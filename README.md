# hefesto-mod-imersao

O **Modo imersão** do Hefesto, numa extensão: um motor de receitas que lê a cena do jogo pela porta
das modificações e a leva ao controle, pela vibração, pelos gatilhos adaptativos, pela luz e, quando
a porta os tiver, pela háptica e pelo alto-falante. Licença GPL-3.0-or-later (`LICENSE`).

> **Aviso.** Extensão independente: não é afiliada à Sony nem endossada por ela. Da internet, a
> extensão só baixa o índice assinado das receitas da comunidade e a receita do jogo aberto (o
> manifesto declara `rede:internet`), e o pedido diz qual jogo está aberto.

**Estado (0.4.0, 02/11/2026):** o formato da receita, o validador, o motor e o universal que vale
em todo jogo, com a porta de mentira das provas. A extensão ainda não toca o controle de verdade: o Hefesto de hoje recusa o campo
`modos_de_aba` do manifesto, e o install espera o Hefesto que o conhece.

## Como funciona

```
sentidos  →  derivados  →  estados  →  regras  →  efeitos  →  a porta
(eventos)    (contas)      (histerese)  (quando)   (o mais forte vence)
```

- O processo (`servidor.py`) roda com `python3 -I` e só a biblioteca padrão. A receita se escolhe
  pelo jogo aberto (`perfil.jogo`), pela `jogo.chave` do arquivo (`receita/biblioteca.py`): a sua
  (`$HEFESTO_MOD_DADOS/receitas/*.json`, e o `receita.json` de antes, que vale em todo jogo), a
  estudada (`receitas/estudadas/`), a da comunidade e, sem nenhuma, o **universal**
  (`receitas/universal.json`). A recusada não vale, e o diário diz a linha do erro. A troca entra
  no tique seguinte e devolve ao jogo o canal da receita velha; a coluna «Agora» da janela diz qual
  vale.
- As `entradas` da receita são as opções da janela «Configurar»: o motor lê o `opcoes.json` salvo
  e o arrasto ao vivo. A opção «Receita» em «Universal» ignora a receita do jogo.
- A janela tem seis abas. Geral: a Força (multiplica tudo o que sai; em 0, nada), a Receita, «O
  golpe vai para» (quem levou, ou todos os controles) e, com um jogo em cena, a «Memória neste
  jogo» do Hefesto. Sentidos e Canais: cada um se desliga, e o sentido desligado desassina o tópico
  dele (a Tela nasce desligada). Efeitos: as entradas do universal, com a cor do dano e o intervalo
  do susto; cada linha só aparece quando a receita que vale tem o efeito dela (o `@presente` pelos
  `presentes` do estado). «Procurar receitas» fica na Geral. «Ensinar
  este jogo»: a página do Estúdio. Os ajustes de Geral, Sentidos e Canais moram em `opcoes.py` e
  valem em toda receita.
- Na Geral, cada controle conectado é um cartão com a chave «Sente os efeitos»: o desligado não
  recebe nada da extensão, e a escolha fica em `controles.json`, pelo número do jogador. A coluna
  «Agora» mostra o clima da cena (o derivado `tensao`, de 0 a 10) no «Nível» e, nas linhas, os
  sentidos lendo agora, a memória que espera a chave e o último efeito tocado, com a hora.
- O `jogo.memoria` só chega ao motor com a «Memória neste jogo» ligada (o `memoria` do
  `perfil.trocou`), em toda receita; no jogo com anticheat, o aviso é o do Hefesto.
- Assina os tópicos que a receita lê, o que o jogo escreve nos canais em que ela escreve
  (`jogo.vibracao`, `jogo.haptica`, `jogo.gatilho`), a `conexao` e o `perfil.jogo`; o tópico que a receita lê e a
  porta ainda não entrega vai ao diário, e o sentido dele fica parado.
- Os sentidos universais (`sentidos/`) leem a porta e o tempo e publicam no próprio tópico, que a
  receita lê como lê a porta: `sentido.som` (o estalo do jogo, com o lado), `sentido.rumble`
  (pulso, rajada e batimento; os níveis `tensao` e `dano_recente`), `sentido.microfone` (o
  `silencio` longo e o `sobressalto`), `sentido.tela` (o `dano_recente`), `sentido.golpe` (o ataque
  seguido do pulso do jogo em até 150 ms) e `sentido.quietude` (o controle parado, sem contar o
  giro que o próprio motor causa, e o controle largado na mesa). Ler um sentido pede a permissão
  de cada origem dele.
- O laço roda a 60 Hz. Um estado sobe pela condição, desce com histerese e fica de pé um tempo
  mínimo. A regra dispara na subida da condição, com `espera_ms`, e o `senao` vale na descida.
- Duas regras no mesmo canal do mesmo controle não somam: vence a mais forte, a `prioridade`
  desempata, e depois a mais recente.
- O caminho do controle do jogo se mede ao vivo (`motor/caminho.py`): o canal em que o jogo
  escreveu nos últimos 3 s está ocupado (o gatilho, até o jogo trocar o efeito), e nele a receita
  só sai quando é mais forte que o jogo; no canal livre, ela sai inteira. A luz do jogo se aprende pela recusa `-32011` da porta, e a máscara
  Xbox ou Nintendo (`jogo.identidade`, quando a porta o entregar) deixa a luz e o gatilho livres.
  A receita nunca declara o caminho.
- A saída escreve só o que mudou, sob o teto do tato vivo (12 escritas por segundo por controle,
  40 no total); o zero que solta passa sempre.
- O peso da mira sai pelo `mira.peso`, fora do teto do tato vivo: o pedido vale 800 ms e se
  renova a cada 500 ms enquanto o efeito vale; com o ganho em 1, nada se pede, e o Hefesto
  devolve a mira no prazo. O «Peso da mira» da aba Efeitos (nasce ligado), a Força, «O golpe vai
  para» e o controle calado valem para ele como para os outros canais. A recusa `-32013` (o jogo
  com anticheat, ou o controle fora do modo da extensão) cala a mira daquele controle por 5 s, ou
  até o jogo trocar, sem linha no diário: a chave ligada com o jogo aberto vale no pedido seguinte.
  A porta sem o método cala o canal, com uma linha no diário.

## A receita (formato 1)

JSON de até 64 KB, validado sem perdão: campo desconhecido, chave repetida e expressão fora da
gramática recusam, sempre com a linha.

| campo | o que é |
| --- | --- |
| `formato`, `motor` | `1` e a faixa do motor (`">=1,<2"`); obrigatórios |
| `jogo` | `chave`, `janela`, `builds{steam_buildid}`, `leitura_de_memoria` (`nao`, `nunca` ou `pede`) |
| `permissoes` | o que a receita lê (`ler:<tópico>`); o sentido que lê sem declarar recusa |
| `entradas` | `deslizante`, `ligado` ou `cor` da pessoa (`$nome` nas expressões; a cor só na `cor` da luz) |
| `sentidos` | o que chega da porta: `nivel`, `estado` ou `evento`, com `campo` (o caminho no evento, com o índice da lista: `pedido.1` é o forte do `jogo.vibracao`), `igual`, `escala`, `limiar` |
| `derivados` | uma expressão, ou um acumulador (`sobe_com`, `passo`, `meia_vida_ms`) |
| `estados` | `quando`, `histerese`, `minimo_ms` |
| `efeitos` | `motor`, `gatilho`, `luz`, `haptica` (`coracao`, `susto`, `estalo`), `som` (`susto`, `estalo` ou o `recorte` do estalo do jogo), `leds` (as luzes de jogador do lado, até 600 ms), `mira` (o `ganho` do giroscópio, de 0,3 a 1, pelo `mira.peso`) |
| `regras` | `quando`, `entao`, `senao`, `prioridade`, `espera_ms` (número ou expressão), `para` (`todos`, `quem_levou` ou `p1`..`p4`) |
| `confere` | a faixa esperada de um sentido, ou a concordância entre dois |

As expressões têm números, nomes, `$entrada`, `+ - * /`, comparações, `e`, `ou`, `nao` e as
funções `min`, `max`, `abs`, `limita` e `mapeia`. Não há `eval`: a gramática é fechada, com teto de
512 caracteres, 64 nós e 32 níveis um dentro do outro, e dependência circular recusa com o caminho
do ciclo.

O gatilho fala os sete modos de um jogo de PS5, nas faixas que o console aceita (a arma começa de 2
a 7 e termina de 3 a 8, a força vai de 1 a 8, a frequência de 1 a 255; a frequência 0 desliga, e
o gatilho sem força é o modo `desliga`). O coração, o susto e o estalo são padrões PCM a 48 kHz (`motor/efeitos.py`); sem a háptica
na porta, o envelope do padrão sai pelo motor.

Exemplos em `testes/receitas/`.

## O universal

`receitas/universal.json` vale em todo jogo sem receita: o estalo forte de um lado vibra o motor
daquele lado (e as luzes de jogador do lado, com «Lado na luz», que nasce desligado); a rajada de
rumble pinta a barra de vermelho no controle que levou; o golpe dado pede o impacto no gatilho que
atacou; a tensão (o batimento do rumble, o dano recente, o silêncio longo e o controle parado na
mão, juntos) toca o coração de 60 a 140 bpm, e o barulho súbito no microfone o acalma; o estalo
forte com a cena tensa toca o susto, o recorte do próprio estalo do jogo no alto-falante. O perigo
(a tensão e o dano recente) pesa a mira de 1 a 0,6, e o alívio a devolve.

## As receitas estudadas

Em `receitas/estudadas/`, uma por jogo, valem quando o jogo abre e quem joga não tem a própria:

- `minecraft-dungeons-ii.json` (Steam 1912410): o jogo manda nos gatilhos; a receita soma o coração
  pelo batimento do rumble, o susto, o lado pelo som, a barra vermelha na rajada e o impacto do
  golpe, que só troca o gatilho do jogo quando é mais forte, e pesa a mira de 1 a 0,6 no perigo.
  Sem memória.

## O Estúdio

O botão «Ensinar este jogo» (página em `estudio/pagina/`) guia com frases curtas, e o botão do meio
do controle marca o gesto. O caçador do valor (só com a «Memória neste jogo» ligada), o do som e
o do canto da tela guardam o que muda com o gesto e descartam o que muda sem ele; o achado vira um
`estado` na sua receita, com o nome que você der. «Blocos» mostra a receita como QUANDO e FAÇA, e
«Gravar» e «Tocar» repetem cinco minutos de jogo com a receita de agora, sem abrir o jogo.
«Grafo» desenha a receita do sentido ao efeito e marca o nó com erro (ciclo, órfão, tipo errado);
«Texto» mostra o JSON, validado a cada tecla, com «Exportar» e «Importar».

## As receitas da comunidade

Moram no repositório `hefesto-receitas-imersao` (as receitas são CC0). A extensão baixa o índice
uma vez por dia, ou no «Procurar receitas», e só o aceita com a assinatura que fecha com a chave
pública dela; depois baixa só a receita do jogo aberto, que tem de bater com a soma do índice e
passar no validador. Vale a sua, depois a estudada, depois a da comunidade. A receita que lê a
memória diz isso na página e no «Agora», e espera a «Memória neste jogo» da aba Geral.

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
