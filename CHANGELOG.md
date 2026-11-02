# Mudanças

## 0.4.3 (02/11/2026)

- O Estúdio monta QUANDO e FAÇA (`estudio/blocos.py`): cada bloco é uma regra da receita, com a
  condição, os efeitos (a frase de cada um como dica), a prioridade e para quem; a ida e a volta
  sai igual, e «Montar» grava a receita só validada. «Gravar» guarda até cinco minutos de sinais
  (`estudio/linha_do_tempo.py`: as bandas do som, a vibração do jogo, a tela e a memória, nunca o
  microfone), e «Tocar» os repete com a receita de agora, sem o jogo aberto.

## 0.4.2 (02/11/2026)

- O Estúdio caça o que o jogo esconde (`estudio/cacador.py`, página em `estudio/pagina/`): o botão
  «Ensinar este jogo» guia com frases curtas («perca vida agora», «agora não faça nada», «recupere
  vida»), e o gesto se marca pelo botão do meio. Três caçadores, com a mesma regra (guarda o que
  muda com o gesto e descarta o que muda sem ele): o valor da memória, só com a chave «Memória» do
  jogo ligada, pela varredura de candidatos da porta; a impressão do estalo, em números de até
  4 KB, nunca o áudio; e a região da tela, em frações de 0 a 1. O achado vira um `estado` na
  receita de quem joga, com o nome dado, e a receita só se grava validada.
- O formato da receita ganha a `impressao` no evento de `jogo.som` e a `regiao` no nível de
  `jogo.tela`; o motor reconhece o estalo pela impressão e lê a memória pelo nome do sentido.

## 0.4.1 (02/11/2026)

- O pedido vivo (o coração, a luz, a vibração contínua) só se reescreve quando o degrau muda (força de 0,05 em
  0,05, batimento de 4 em 4 bpm), com intervalo mínimo por canal e controle e sempre com vaga no teto para o
  evento: o coração do universal cai de 12 para 2 escritas por segundo, e o estalo e o susto saem no tique deles.

## 0.4.0 (02/11/2026)

- A receita se escolhe pelo jogo aberto (`perfil.jogo`), pela `jogo.chave` de cada arquivo: vale a
  de quem joga (`$HEFESTO_MOD_DADOS/receitas/*.json`), depois a estudada que vem com a extensão
  (`receitas/estudadas/`), depois a da comunidade; sem nenhuma, o universal. O jogo fechado volta ao
  universal. A troca entra no tique seguinte, e o canal que a receita velha usava se solta e volta ao
  jogo. O `receita.json` de antes segue valendo como a receita de quem joga sem jogo próprio.
- As `entradas` da receita são opções da janela «Configurar»: o manifesto declara a opção
  «Receita» (Pelo jogo ou Universal) e «Lado na luz», e o motor lê o valor salvo
  (`opcoes.json`, relido a cada meio segundo) e o arrasto ao vivo (`extensao.opcao`). O
  deslizante fica entre o mínimo e o máximo da entrada, e o «ligado» só vale verdadeiro ou falso.
- A receita estudada do Minecraft Dungeons II (`receitas/estudadas/minecraft-dungeons-ii.json`), só
  do estudo, sem memória: o coração em dois degraus pelo batimento do rumble do jogo, o susto pelo
  estalo forte na cena tensa, o lado pelo som, a barra vermelha na rajada e o impacto do golpe no
  gatilho. Os gatilhos do jogo só cedem ao impacto mais forte que eles.
- A coluna «Agora» da janela diz qual receita vale (`acessorios.estado`, no campo «Perfil»): a
  sua, a estudada, a da comunidade ou o universal.

## 0.3.1 (01/11/2026)

- A escrita que a porta recusa com `-32011` devolve a conta da saída ao que a porta aceitou antes,
  que segue no controle: quando a receita solta o canal, ou a extensão sai, o zero do motor, do
  gatilho e da háptica escritos antes sai. O zero que a porta recusa não se repete com o canal
  solto, e a extensão que sai o tenta uma vez mais. Vale de P1 a P4, no cabo e no rádio.

## 0.3.0 (01/11/2026)

- O motor lê o caminho do controle do jogo ao vivo (`motor/caminho.py`): por controle e por canal
  (motor, háptica, gatilho e luz), o que o jogo escreveu nos últimos 3 s; o efeito do jogo no
  gatilho segura a vaga até o jogo trocá-lo. No canal ocupado, a
  receita só sai mais forte que o jogo; no livre, sai inteira. Vale de P1 a P4, no cabo e no rádio.
- A luz do jogo, que não tem tópico, se aprende pela recusa `-32011` da porta (com `data.vence` em
  `jogo`, ou sem `data`); a recusa que outra extensão vence não conta, e a escrita recusada não se
  repete enquanto o mesmo valor continuar pedido.
- A máscara Xbox ou Nintendo de `jogo.identidade` deixa a luz e o gatilho da receita inteiros
  desde o começo; o tópico entra na assinatura quando a porta o entregar.
- O rumble do jogo sem a batida de 250 ms por 600 ms vale zero, e o `jogo.fechou` solta tudo.
- Sem `haptica.tocar` na porta, o padrão que cai no motor disputa com o motor do jogo.
- O coração que a extensão toca cala o giro só nos golpes do padrão, e quem se mexe entre eles
  desliga o «parado»: o coração não se sustenta sozinho.
- O controle largado (sem leitura de movimento por 10 s) sai da conta do «parado», e com todos
  largados o silêncio não sobe a tensão: o controle na mesa não liga o coração.

## 0.2.0 (01/11/2026)

- O universal vale em todo jogo (`receitas/universal.json`): sem receita, ou com ela recusada, é
  ele que roda, e não mais a receita vazia.
- Os sentidos universais (`sentidos/`): o estalo do som do jogo com o lado, o rumble em pulso,
  rajada e batimento, o silêncio e o barulho súbito do microfone, o dano da tela, o golpe dado e o
  controle parado, que ignora o giro enquanto o controle vibra e 100 ms depois.
- O efeito `leds` (as luzes de jogador do lado, por máscara e prazo de até 600 ms, por `leds.set`)
  e o som `recorte` (o estalo do próprio jogo, pelo `t` do `jogo.som`); sem os métodos na porta,
  os dois se calam e o diário diz qual.

## 0.1.0 (01/11/2026)

- O Modo imersão nasce como extensão: o manifesto com `api: ">=2,<3"`, o «Modo imersão» em
  `modos_de_aba`, as permissões de leitura que a receita usa e `rede:nenhuma`.
- O formato 1 da receita, validado sem perdão e com a linha de cada erro: campo desconhecido,
  chave repetida, expressão fora da gramática, ciclo, gatilho fora da faixa do console e receita
  acima de 64 KB recusam.
- O motor a 60 Hz: estados com histerese e tempo mínimo, regras sem `eval`, o mais forte vence em
  cada canal, e a saída sob o teto do tato vivo.
- Sem receita, vale o universal.
