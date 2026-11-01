# hefesto-mod-imersao

O **Modo imersão** do Hefesto, numa extensão: um motor de receitas que lê a cena do jogo pela porta
das modificações e a leva ao controle, pela vibração, pelos gatilhos adaptativos, pela luz e, quando
a porta os tiver, pela háptica e pelo alto-falante. Licença GPL-3.0-or-later (`LICENSE`).

> **Aviso.** Extensão independente: não é afiliada à Sony nem endossada por ela. Nada sai deste
> computador: o manifesto declara `rede:nenhuma`.

**Estado (0.1.0, 01/11/2026):** o formato da receita, o validador e o motor, com a porta de mentira
das provas. A extensão ainda não toca o controle de verdade: o Hefesto de hoje recusa o campo
`modos_de_aba` do manifesto, e o install espera o Hefesto que o conhece.

## Como funciona

```
sentidos  →  derivados  →  estados  →  regras  →  efeitos  →  a porta
(eventos)    (contas)      (histerese)  (quando)   (o mais forte vence)
```

- O processo (`servidor.py`) roda com `python3 -I` e só a biblioteca padrão. Lê a receita em
  `$HEFESTO_MOD_DADOS/receita.json`; sem ela, ou com ela recusada, vale o **universal** (a receita
  vazia), e o diário diz a linha do erro.
- Assina só os tópicos que a receita lê, mais `conexao`.
- O laço roda a 60 Hz. Um estado sobe pela condição, desce com histerese e fica de pé um tempo
  mínimo. A regra dispara na subida da condição, com `espera_ms`, e o `senao` vale na descida.
- Duas regras no mesmo canal do mesmo controle não somam: vence a mais forte, a `prioridade`
  desempata, e depois a mais recente.
- A saída escreve só o que mudou, sob o teto do tato vivo (12 escritas por segundo por controle,
  40 no total); o zero que solta passa sempre.

## A receita (formato 1)

JSON de até 64 KB, validado sem perdão: campo desconhecido, chave repetida e expressão fora da
gramática recusam, sempre com a linha.

| campo | o que é |
| --- | --- |
| `formato`, `motor` | `1` e a faixa do motor (`">=1,<2"`); obrigatórios |
| `jogo` | `chave`, `janela`, `builds{steam_buildid}`, `leitura_de_memoria` (`nao` ou `pede`) |
| `permissoes` | o que a receita lê (`ler:<tópico>`); o sentido que lê sem declarar recusa |
| `entradas` | deslizantes da pessoa (`$nome` nas expressões) |
| `sentidos` | o que chega da porta: `nivel`, `estado` ou `evento`, com `campo`, `igual`, `escala`, `limiar` |
| `derivados` | uma expressão, ou um acumulador (`sobe_com`, `passo`, `meia_vida_ms`) |
| `estados` | `quando`, `histerese`, `minimo_ms` |
| `efeitos` | `motor`, `gatilho`, `luz`, `haptica` (`coracao`, `susto`, `estalo`), `som` |
| `regras` | `quando`, `entao`, `senao`, `prioridade`, `espera_ms`, `para` (`todos`, `quem_levou` ou `p1`..`p4`) |
| `confere` | a faixa esperada de um sentido, ou a concordância entre dois |

As expressões têm números, nomes, `$entrada`, `+ - * /`, comparações, `e`, `ou`, `nao` e as
funções `min`, `max`, `abs`, `limita` e `mapeia`. Não há `eval`: a gramática é fechada, com teto de
512 caracteres e 64 nós, e dependência circular recusa com o caminho do ciclo.

O gatilho fala os sete modos de um jogo de PS5, nas faixas que o console aceita (a arma começa de 2
a 7 e termina de 3 a 8, a força vai de 1 a 8, a frequência de 1 a 255; `desliga` é o modo sem
força). O coração, o susto e o estalo são padrões PCM a 48 kHz (`motor/efeitos.py`); sem a háptica
na porta, o envelope do padrão sai pelo motor.

Exemplos em `testes/receitas/`.

## Instalar

```bash
./install.sh --yes     # entrega a pasta ao Hefesto: hefesto-dualsense4unix mod instalar <pasta> --sim
./uninstall.sh         # hefesto-dualsense4unix mod remover imersao
```

Os dois recusam `sudo`. `HEFESTO_CLI` aponta para outra CLI do Hefesto.

## Provas

```bash
python -m pytest -q testes/
```

Rodam sem controle, sem daemon e sem rede: a porta é de mentira, num socket próprio.
