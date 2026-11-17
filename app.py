"""
LOJA-USEME - Aplicação Flask (lado do cliente)

O que este arquivo faz:
- Página inicial (index.html)
- Catálogo de produtos com busca, filtro e ordenação (produtos.html)
- Detalhe de um produto (produto_detalhe.html)
- Carrinho de compras (carrinho.html)

Regras importantes (segurança):
- Preço e estoque SEMPRE vêm do banco de dados, nunca do navegador.
- Formulários POST têm token CSRF.
- Chave secreta vem do arquivo .env (nunca fica escrita no código).

Ainda NÃO está neste arquivo (próximas etapas):
- Cadastro/login de clientes, checkout, pagamento, painel admin.
"""

import os
import secrets
import sqlite3
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent

# Lê o arquivo .env se a biblioteca python-dotenv estiver instalada.
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

app = Flask(__name__)  # usa as pastas padrão: templates/ e static/

# Em produção, defina SECRET_KEY no .env. Sem ela, gera uma chave temporária
# (as sessões/carrinhos se perdem quando o servidor reinicia).
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["DATABASE"] = os.environ.get("DATABASE_PATH", str(BASE_DIR / "loja.db"))
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") == "production"

QTD_MAXIMA_POR_ITEM = 10  # limite por linha do carrinho
PRODUTOS_POR_PAGINA = 12

CATEGORIAS = ["Camisetas", "Calças", "Vestidos", "Jaquetas", "Acessórios"]
ORDENACOES = {
    "novos": "id DESC",
    "menor_preco": "preco_centavos ASC",
    "maior_preco": "preco_centavos DESC",
    "nome": "nome COLLATE NOCASE ASC",
}


# ---------------------------------------------------------------------------
# Banco de dados (SQLite)
# ---------------------------------------------------------------------------
def get_db():
    """Abre (ou reaproveita) a conexão com o banco durante a requisição."""
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def fechar_db(_erro=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# Produtos de exemplo, só para o catálogo não começar vazio.
PRODUTOS_EXEMPLO = [
    ("Camiseta Básica Algodão", "Camiseta 100% algodão, corte reto e macia.", 5990, "Camisetas", 40, "camiseta-basica.jpg", "P,M,G,GG"),
    ("Camiseta Oversized", "Modelagem ampla, ideal para o dia a dia.", 7990, "Camisetas", 25, "camiseta-oversized.jpg", "P,M,G"),
    ("Calça Jeans Slim", "Jeans com elastano, confortável e durável.", 15990, "Calças", 18, "calca-jeans.jpg", "38,40,42,44"),
    ("Calça de Alfaiataria", "Tecido leve, perfeita para o trabalho.", 17990, "Calças", 12, "calca-alfaiataria.jpg", "38,40,42,44"),
    ("Vestido Midi Floral", "Vestido leve com estampa floral.", 18990, "Vestidos", 10, "vestido-floral.jpg", "P,M,G"),
    ("Jaqueta Jeans", "Clássica, combina com tudo.", 22990, "Jaquetas", 8, "jaqueta-jeans.jpg", "P,M,G,GG"),
    ("Boné Aba Curva", "Ajustável, tecido resistente.", 4990, "Acessórios", 30, "bone.jpg", "Único"),
    ("Cinto de Couro", "Couro legítimo com fivela metálica.", 8990, "Acessórios", 0, "cinto.jpg", "Único"),
]


def iniciar_banco():
    """Cria a tabela de produtos e insere os exemplos se estiver vazia."""
    db = sqlite3.connect(app.config["DATABASE"])
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS produtos (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            nome           TEXT    NOT NULL,
            descricao      TEXT    NOT NULL DEFAULT '',
            preco_centavos INTEGER NOT NULL CHECK (preco_centavos >= 0),
            categoria      TEXT    NOT NULL,
            estoque        INTEGER NOT NULL DEFAULT 0 CHECK (estoque >= 0),
            imagem         TEXT    NOT NULL DEFAULT '',
            tamanhos       TEXT    NOT NULL DEFAULT 'Único',
            ativo          INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    if db.execute("SELECT COUNT(*) FROM produtos").fetchone()[0] == 0:
        db.executemany(
            """
            INSERT INTO produtos
                (nome, descricao, preco_centavos, categoria, estoque, imagem, tamanhos)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            PRODUTOS_EXEMPLO,
        )
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------
def formatar_brl(centavos):
    """Converte 5990 -> 'R$ 59,90'."""
    reais, cents = divmod(int(centavos), 100)
    return f"R$ {reais:,}".replace(",", ".") + f",{cents:02d}"


app.jinja_env.filters["brl"] = formatar_brl


def produto_para_dict(linha):
    """Transforma a linha do banco em dict e separa a lista de tamanhos."""
    produto = dict(linha)
    produto["lista_tamanhos"] = [t.strip() for t in produto["tamanhos"].split(",") if t.strip()]
    return produto


def buscar_produto(produto_id):
    linha = get_db().execute(
        "SELECT * FROM produtos WHERE id = ? AND ativo = 1", (produto_id,)
    ).fetchone()
    return produto_para_dict(linha) if linha else None


def obter_carrinho():
    """
    O carrinho fica na sessão como {"id|tamanho": quantidade}.
    Guardamos só ids e quantidades. Preços são buscados no banco.
    """
    return session.setdefault("carrinho", {})


def calcular_carrinho():
    """
    Monta o resumo do carrinho usando dados REAIS do banco.
    Remove itens que não existem mais e ajusta quantidades acima do estoque.
    Retorna: (itens, subtotal_centavos, total_unidades, avisos)
    """
    carrinho = obter_carrinho()
    itens, avisos = [], []
    subtotal = total_unidades = 0
    restante = {}  # estoque ainda disponível por produto (soma dos tamanhos)

    for chave, qtd in list(carrinho.items()):
        try:
            id_txt, tamanho = chave.split("|", 1)
            produto = buscar_produto(int(id_txt))
        except (ValueError, TypeError):
            produto = None

        if produto is None or tamanho not in produto["lista_tamanhos"]:
            carrinho.pop(chave, None)
            avisos.append("Um item do carrinho não está mais disponível e foi removido.")
            continue

        disponivel = restante.setdefault(produto["id"], produto["estoque"])
        qtd_ok = max(0, min(int(qtd), disponivel, QTD_MAXIMA_POR_ITEM))

        if qtd_ok == 0:
            carrinho.pop(chave, None)
            avisos.append(f"“{produto['nome']}” esgotou e foi removido do carrinho.")
            continue
        if qtd_ok < int(qtd):
            carrinho[chave] = qtd_ok
            avisos.append(f"A quantidade de “{produto['nome']}” foi ajustada para {qtd_ok} (estoque).")

        restante[produto["id"]] = disponivel - qtd_ok
        total_item = produto["preco_centavos"] * qtd_ok
        subtotal += total_item
        total_unidades += qtd_ok
        itens.append(
            {
                "chave": chave,
                "produto": produto,
                "tamanho": tamanho,
                "quantidade": qtd_ok,
                "total_centavos": total_item,
            }
        )

    session.modified = True
    return itens, subtotal, total_unidades, list(dict.fromkeys(avisos))


def ler_inteiro(valor, padrao=None):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return padrao


# ---------------------------------------------------------------------------
# Segurança: CSRF e cabeçalhos
# ---------------------------------------------------------------------------
def gerar_csrf():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


@app.before_request
def verificar_csrf():
    """Bloqueia POSTs sem o token correto."""
    if request.method == "POST":
        enviado = request.form.get("csrf_token", "")
        esperado = session.get("csrf_token", "")
        if not esperado or not secrets.compare_digest(enviado, esperado):
            abort(400, description="Requisição inválida. Recarregue a página e tente de novo.")


@app.after_request
def cabecalhos_seguranca(resposta):
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resposta.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return resposta


@app.context_processor
def variaveis_globais():
    """Variáveis disponíveis em TODOS os templates (ex.: base.html)."""
    return {
        "csrf_token": gerar_csrf,
        "categorias": CATEGORIAS,
        "qtd_carrinho": sum(int(q) for q in session.get("carrinho", {}).values()),
        "nome_loja": "USEME",
    }


# ---------------------------------------------------------------------------
# Rotas - Etapa 1: página inicial
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    destaques = get_db().execute(
        "SELECT * FROM produtos WHERE ativo = 1 AND estoque > 0 ORDER BY id DESC LIMIT 4"
    ).fetchall()
    return render_template("index.html", destaques=[produto_para_dict(p) for p in destaques])


# ---------------------------------------------------------------------------
# Rotas - Etapa 2: catálogo e detalhe do produto
# ---------------------------------------------------------------------------
@app.route("/produtos")
def produtos():
    categoria = request.args.get("categoria", "").strip()
    busca = request.args.get("busca", "").strip()[:60]
    ordem = request.args.get("ordem", "novos")
    pagina = max(1, ler_inteiro(request.args.get("pagina"), 1))

    # A ordenação vem de uma lista fixa (evita SQL injection).
    ordem_sql = ORDENACOES.get(ordem, ORDENACOES["novos"])

    filtros, parametros = ["ativo = 1"], []
    if categoria in CATEGORIAS:
        filtros.append("categoria = ?")
        parametros.append(categoria)
    if busca:
        filtros.append("nome LIKE ?")
        parametros.append(f"%{busca}%")
    where = " AND ".join(filtros)

    db = get_db()
    total = db.execute(f"SELECT COUNT(*) FROM produtos WHERE {where}", parametros).fetchone()[0]
    total_paginas = max(1, -(-total // PRODUTOS_POR_PAGINA))
    pagina = min(pagina, total_paginas)

    linhas = db.execute(
        f"SELECT * FROM produtos WHERE {where} ORDER BY {ordem_sql} LIMIT ? OFFSET ?",
        parametros + [PRODUTOS_POR_PAGINA, (pagina - 1) * PRODUTOS_POR_PAGINA],
    ).fetchall()

    return render_template(
        "produtos.html",
        produtos=[produto_para_dict(p) for p in linhas],
        categoria_atual=categoria if categoria in CATEGORIAS else "",
        busca=busca,
        ordem=ordem if ordem in ORDENACOES else "novos",
        pagina=pagina,
        total_paginas=total_paginas,
        total=total,
    )


@app.route("/produto/<int:produto_id>")
def produto_detalhe(produto_id):
    produto = buscar_produto(produto_id)
    if produto is None:
        abort(404)
    relacionados = get_db().execute(
        """
        SELECT * FROM produtos
        WHERE ativo = 1 AND categoria = ? AND id != ? AND estoque > 0
        ORDER BY id DESC LIMIT 4
        """,
        (produto["categoria"], produto_id),
    ).fetchall()
    return render_template(
        "produto_detalhe.html",
        produto=produto,
        relacionados=[produto_para_dict(p) for p in relacionados],
        qtd_maxima=min(produto["estoque"], QTD_MAXIMA_POR_ITEM),
    )


# ---------------------------------------------------------------------------
# Rotas - Etapa 3: carrinho
# ---------------------------------------------------------------------------
@app.route("/carrinho")
def carrinho():
    itens, subtotal, total_unidades, avisos = calcular_carrinho()
    for aviso in avisos:
        flash(aviso, "aviso")
    return render_template(
        "carrinho.html",
        itens=itens,
        subtotal_centavos=subtotal,
        total_unidades=total_unidades,
        qtd_maxima=QTD_MAXIMA_POR_ITEM,
    )


@app.route("/carrinho/adicionar", methods=["POST"])
def carrinho_adicionar():
    produto_id = ler_inteiro(request.form.get("produto_id"))
    tamanho = request.form.get("tamanho", "").strip()
    quantidade = ler_inteiro(request.form.get("quantidade"), 1)
    destino = request.referrer or url_for("produtos")

    produto = buscar_produto(produto_id) if produto_id else None
    if produto is None:
        flash("Produto não encontrado.", "erro")
        return redirect(url_for("produtos"))
    if tamanho not in produto["lista_tamanhos"]:
        flash("Escolha um tamanho válido.", "erro")
        return redirect(destino)
    if quantidade is None or not 1 <= quantidade <= QTD_MAXIMA_POR_ITEM:
        flash(f"Quantidade deve ser entre 1 e {QTD_MAXIMA_POR_ITEM}.", "erro")
        return redirect(destino)

    carrinho_atual = obter_carrinho()
    chave = f"{produto_id}|{tamanho}"

    # Confere o estoque somando o que já está no carrinho (todos os tamanhos).
    ja_no_carrinho = sum(
        int(q) for k, q in carrinho_atual.items() if k.split("|", 1)[0] == str(produto_id)
    )
    if ja_no_carrinho + quantidade > produto["estoque"]:
        flash(
            f"Estoque insuficiente. Disponível: {produto['estoque']} unidade(s).",
            "erro",
        )
        return redirect(destino)

    nova_qtd = int(carrinho_atual.get(chave, 0)) + quantidade
    carrinho_atual[chave] = min(nova_qtd, QTD_MAXIMA_POR_ITEM)
    session.modified = True
    flash(f"“{produto['nome']}” foi adicionado ao carrinho.", "sucesso")
    return redirect(url_for("carrinho"))


@app.route("/carrinho/atualizar", methods=["POST"])
def carrinho_atualizar():
    chave = request.form.get("chave", "")
    quantidade = ler_inteiro(request.form.get("quantidade"))
    carrinho_atual = obter_carrinho()

    if chave not in carrinho_atual or quantidade is None:
        flash("Item inválido.", "erro")
        return redirect(url_for("carrinho"))

    if quantidade <= 0:
        carrinho_atual.pop(chave)
    else:
        carrinho_atual[chave] = min(quantidade, QTD_MAXIMA_POR_ITEM)
    session.modified = True
    # calcular_carrinho() (na página) ajusta pelo estoque real e avisa se precisar.
    return redirect(url_for("carrinho"))


@app.route("/carrinho/remover", methods=["POST"])
def carrinho_remover():
    obter_carrinho().pop(request.form.get("chave", ""), None)
    session.modified = True
    flash("Item removido do carrinho.", "sucesso")
    return redirect(url_for("carrinho"))


# ---------------------------------------------------------------------------
# Tratamento de erros (texto simples; páginas de erro podem vir depois)
# ---------------------------------------------------------------------------
@app.errorhandler(400)
def erro_400(erro):
    return f"Requisição inválida: {erro.description}", 400


@app.errorhandler(404)
def erro_404(_erro):
    return "Página não encontrada.", 404


@app.errorhandler(500)
def erro_500(_erro):
    return "Erro interno. Tente novamente em instantes.", 500


# ---------------------------------------------------------------------------
# Inicialização
# ---------------------------------------------------------------------------
iniciar_banco()

if __name__ == "__main__":
    # debug só liga se FLASK_DEBUG=1 no .env (nunca em produção).
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
