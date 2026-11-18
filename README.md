# LOJA-USEME

Loja virtual de roupas feita com Flask, voltada para os clientes. O cliente navega pelo catálogo, vê os detalhes dos produtos e monta o carrinho.

> **Status:** em desenvolvimento. As Etapas 1 a 3 (início, catálogo, detalhe e carrinho) estão no `app.py`. Veja a seção [Funcionalidades](#funcionalidades).

## Funcionalidades

**Implementadas no `app.py`**

- Página inicial com produtos em destaque
- Catálogo com busca, filtro por categoria, ordenação e paginação
- Página de detalhe do produto, com produtos relacionados
- Carrinho: adicionar, alterar quantidade e remover itens
- Preço e estoque sempre conferidos no servidor (nunca confiamos no navegador)
- Proteção CSRF nos formulários e cabeçalhos básicos de segurança
- Banco SQLite criado automaticamente, com produtos de exemplo

**Pendentes (próximas etapas)**

- Cadastro e login de clientes
- Checkout e pedidos
- Pagamento (a compra só pode ser confirmada com o retorno do provedor)
- Entregas, trocas, devoluções e reembolsos
- Painel admin protegido
- Atendimento, marketing e relatórios
- Adequação à LGPD
- Testes automatizados (`tests/test_app.py`)
- Páginas de erro personalizadas

## Estrutura de pastas

```
LOJA-USEME/
├── app.py                  # Aplicação Flask (rotas e regras)
├── requirements.txt        # Dependências Python
├── README.md               # Este arquivo
├── .gitignore              # Arquivos ignorados pelo Git
├── .env.example            # Exemplo de configuração
├── templates/              # Páginas HTML
│   ├── base.html           # Estrutura comum das páginas
│   ├── index.html          # Página inicial
│   ├── produtos.html       # Catálogo
│   ├── produto_detalhe.html# Detalhe de um produto
│   └── carrinho.html       # Carrinho de compras
├── static/
│   ├── css/style.css       # Estilos
│   ├── js/main.js          # Interações da interface
│   └── images/             # Imagens dos produtos
├── tests/
│   └── test_app.py         # Testes (etapa futura)
└── notebooks/
    └── exploracao.ipynb    # Opcional
```

## Como rodar localmente

Você precisa do Python 3.10 ou mais novo.

```bash
# 1. Crie e ative um ambiente virtual
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Instale as dependências
pip install -r requirements.txt

# 3. Crie o arquivo de configuração
cp .env.example .env             # Windows: copy .env.example .env
# Abra o .env e preencha a SECRET_KEY (veja abaixo)

# 4. Inicie o servidor
python app.py
```

Acesse **http://127.0.0.1:5000** no navegador.

### Configuração (.env)

| Variável        | Para que serve                                              |
|-----------------|-------------------------------------------------------------|
| `SECRET_KEY`    | Chave que protege as sessões e o carrinho. **Obrigatória em produção.** |
| `DATABASE_PATH` | Caminho do arquivo SQLite (padrão: `loja.db` na raiz).      |
| `FLASK_DEBUG`   | `1` liga o modo de depuração. Use só no seu computador.     |
| `FLASK_ENV`     | `production` ativa o cookie de sessão seguro (exige HTTPS). |

Para gerar uma `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

> Sem `SECRET_KEY`, o app gera uma chave temporária e os carrinhos se perdem a cada reinício.

## Banco de dados

- Usa **SQLite**, no arquivo `loja.db`, criado sozinho na primeira execução.
- Na primeira vez, 8 produtos de exemplo são inseridos.
- Os preços ficam em **centavos** (inteiros), para evitar erros de arredondamento.
- Para recomeçar do zero, apague o `loja.db` e inicie o app de novo.

## Testes

A pasta `tests/` ainda não tem testes. Quando existirem:

```bash
pytest
```

## Publicação (produção)

1. Defina `SECRET_KEY` e `FLASK_ENV=production` nas variáveis de ambiente do servidor (não suba o `.env` para o Git).
2. Use HTTPS. O cookie de sessão seguro só funciona com ele.
3. Não use `python app.py` em produção. Use um servidor próprio:
   - Linux/Mac: `gunicorn app:app`
   - Windows: `waitress-serve app:app`
4. Garanta que o arquivo do banco fique em um local com **backup** e que persista entre reinícios. Em muitas hospedagens, o disco é apagado a cada nova publicação.
5. Para muitos acessos simultâneos, considere trocar o SQLite por PostgreSQL.

## O que depende de integrações externas

Estas partes **não funcionam sozinhas**: precisam de contratação e configuração de serviços de terceiros.

- **Pagamento:** provedor como Mercado Pago, Stripe ou Pagar.me (confirmação via retorno do provedor).
- **Frete e entrega:** cálculo e rastreio via Correios ou transportadoras.
- **E-mail:** envio de confirmações e recuperação de senha (SMTP ou serviço de e-mail).
- **Hospedagem, domínio e HTTPS:** necessários para publicar.

## Segurança

- Preços, totais e estoque são calculados no servidor.
- Formulários protegidos por token CSRF.
- Consultas ao banco usam parâmetros (evita SQL injection).
- Segredos ficam no `.env`, fora do código e fora do Git.

## Licença

Defina a licença do projeto aqui.
