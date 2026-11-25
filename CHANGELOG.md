# Mudanças

## Na próxima versão

- A receita que lê a memória do jogo ou uma região da tela passa a assinar na língua do Hefesto: a leitura
  vai com o endereço e a faixa do `buildid`, a região com a cor, e uma recusa da assinatura vai ao diário uma vez
  por receita, sem derrubar os outros tópicos nem a extensão ao nascer. O formato pede a `cor` da região e
  aceita o `hz` da leitura; a leitura tem até 7 `saltos`. O tópico `bateria`, que nenhuma receita lê e a extensão
  não assina, sai do formato: a receita que o pede é recusada com a linha.
- No Minecraft Dungeons II o R2 passa a ter a resistência de arco ao puxar enquanto o jogo está aberto, em
  cada controle: o impacto do golpe toca por cima e, ao acabar, o arco volta. A opção «R2 ao puxar», no
  cartão «Impacto nos gatilhos», escolhe o efeito (a lista dos gatilhos e «Solto», que deixa o gatilho
  livre); nasce em «Arco». A chave do cartão desligada solta o arco junto com o impacto.
- O gatilho de um efeito que vale enquanto a regra vale se renova a cada 2,5 s e sai com prazo, para a
  porta não o soltar; ao acabar, o gatilho volta ao que o perfil diz na hora.
- O efeito que vale enquanto a regra vale alcança também o controle que liga, volta ou troca de número
  depois do início.
- O impacto, o susto e a luz que caem no teto de efeitos do controle não se perdem: saem logo que há
  vaga, em cada controle. O que a porta recusa por outro motivo se tenta de novo só a cada 2,5 s, e
  o diário diz a recusa uma vez por efeito, com o motivo «teto» quando foi o teto.
- A luz do dano volta à cor de antes quando o efeito acaba, e o dano seguinte, com a mesma cor, pisca
  de novo: a luz e o impacto no gatilho saem com o prazo do efeito, e o Hefesto que devolve o que
  havia o faz sozinho. O impacto já não apaga o gatilho do perfil ao terminar quando o Hefesto o
  devolve.
- Sem jogo aberto, a extensão deixa o processador em paz: o laço dorme até acontecer algo (um evento, uma
  mudança na janela ou a renovação do som no corpo) e volta aos 60 por segundo com um jogo em cena, em
  qualquer controle. A escolha da receita não relê as receitas que não mudaram no disco.
- A extensão que perde uma tarefa interna não fica de pé sem tocar: ela sai com o erro no diário, e o
  Hefesto a sobe de novo. Uma linha enorme da porta ou um estilo torto no arquivo de opções não a
  derrubam.

## 0.5.6 (16/11/2026)

- A janela perde a coluna «Agora»: no alto, uma faixa diz se a extensão está tocando, com o nome do
  jogo, calada, com o motivo (a Intensidade em zero, nenhum controle que sente, ou a frase da porta
  que recusa cada um), ou esperando um jogo, e as linhas dizem o estilo, o ajuste que vale, quem
  sente, quem não recebe nada e, só no Terror, a tensão da cena em palavras (Calma, Atenta, Tensa,
  Pânico). Saem o nível de 0 a 10 e a curva do clima.
- Três abas: Sentir (o Ajuste, o Estilo e a Intensidade; cada sentido com o medidor do que ele lê
  agora; os canais do controle), Efeitos (um cartão por efeito, com o «Testar» no pé; os do Terror
  marcados) e Controles (um cartão por controle, pela cor do plástico).
- A «Receita» vira o «Ajuste», em «Automático» ou «Sempre o universal»; a escolha de antes vira a
  de mesmo sentido. Saem «O golpe vai para» (o golpe vai a quem levou) e «Procurar receitas» (o
  índice da comunidade segue baixando sozinho a cada jogo que abre).
- A resposta do «Testar» leva o nome do plástico de cada controle.
- Pede o Hefesto que conhece o `cartao` das ações, a `marca` das opções e a `situacao` e as
  `leituras` do estado.

## 0.5.5 (16/11/2026)

- O Modo imersão toca em todo estilo: o Som no corpo (o grave do som do jogo na vibração fina,
  junto com a TV) e os Gatilhos que vibram (apertar o L2 vibra o motor esquerdo, e o R2 o direito,
  no tipo escolhido) valem em todo jogo e com toda receita, em cada controle que sente, pelo
  `corpo.ligar` da porta. A aba Efeitos ganha os dois cartões, com a força de cada um (70 % de
  padrão) e o tipo dos gatilhos. O coração, o alívio, o susto e o peso da mira seguem só no Terror.
  A linha do minuto conta cada pedido aceito e cada recusa.
- Os botões de testar dizem o que aconteceu: a extensão responde ao clique com uma linha por
  controle, tocou ou não tocou, com o motivo em palavras («no Modo Nativo o jogo fala direto com o
  controle», «o controle está desligado na extensão», «o efeito está desligado na janela»).
- Pede o Hefesto que conhece o `corpo.ligar` (permissão `escrever:corpo`) e o `responde` das
  ações; a permissão nova pede o «sim» de quem usa ao atualizar.

## 0.5.4 (16/11/2026)

- O jogo que vibra pela háptica, e não pelo motor (o Sackboy), chega ao dano, ao batimento e ao
  golpe: a rajada, o pulso e o golpe dado leem os dois caminhos, e o jogo que vibra pelos dois vale
  pelo mais forte. A receita que lê o `sentido.rumble` ou o `sentido.golpe` declara também
  `ler:jogo.haptica`.
- O diário e o cartão de cada controle na janela falam pela cor do plástico também quando o Hefesto
  a descobre depois que o controle conecta: a extensão pede a lista de novo a cada 5 s enquanto um
  controle está sem cor, e a cada minuto, antes da linha do diário. Sem a cor, vale «Jogador N».
- O Estúdio sai da extensão: a janela fica com três abas, Jogo, Sentidos e Efeitos, sem «Ensinar
  este jogo». As receitas estudadas, as da comunidade e a sua receita já gravada continuam valendo.

## 0.5.3 (16/11/2026)

- A janela ganha o controle vivo: o desenho do «Mapa dos controles» na coluna «Agora», com as peças
  que a extensão acabou de mexer acesas no controle escolhido (um chip por controle, pela cor do
  plástico), e a curva do clima com o limiar da receita.
- As abas ficam quatro: Jogo (receita, estilo, força, golpe e o cartão de cada controle), Sentidos,
  Efeitos (os canais numa fileira de chaves no topo e um cartão por efeito, com a força, o tipo e o
  que mais ele tem) e «Ensinar este jogo». O Estúdio abre no grafo da receita e ocupa a aba; o
  «Procurar receitas» mora na aba Jogo.
- Pede o Hefesto que conhece o controle vivo, o `cartao`, o `canal` e o `abas` do manifesto. Um
  Hefesto mais velho recusa a instalação e diz por quê.

## 0.5.2 (14/11/2026)

- A universal segue o estilo do jogo: deixa de tocar o terror em todo jogo. Num jogo de terror,
  continuam o coração, o susto e o peso da mira. Num de tiro, ficam o golpe com lado e o impacto
  no gatilho, sem coração e sem susto. Na corrida o golpe é mais leve; na luta, inteiro; na
  aventura e na plataforma, leve; no ritmo, a batida chega ao corpo sem impacto no gatilho. Sem
  estilo, vale o geral, sem coração e sem susto.
- A opção «Estilo», na aba Geral, troca o estilo à mão; «Pelo jogo» é o padrão. O «Agora» diz o
  estilo que vale.
- Pede o Hefesto que publica o estilo do jogo (`ler:jogo.estilo`). Um Hefesto mais velho recusa a
  instalação e diz por quê.

## 0.5.1 (14/11/2026)

- Aba nova, «Tipos»: você escolhe a forma de cada efeito que vibra. O coração, o alívio e o susto no
  tato têm Batida, Pancada, Pulso, Tremor, Estalo ou Onda; o golpe com lado tem as mesmas e o
  Contínuo, o golpe inteiro de antes. O impacto no L2 e no R2 tem os efeitos da aba Gatilhos do
  Hefesto (Vibração, Resistência, Disparo, Arco, Galope, Metralhadora, Rampa de força, Curva de força
  e Vibração por posição). No padrão, tudo toca como antes.
- Cada tipo tem o botão de testar ao lado: o efeito toca uma vez em todo controle ligado, pelo cabo
  ou pelo rádio, na Força da janela e na de cada controle.
- O universal e a receita do Minecraft Dungeons II leem a escolha; a receita que não a cita toca como
  na 0.5.0.

## 0.5.0 (14/11/2026)

- O susto se ajusta numa aba própria, «Susto»: a duração do pico (de 100 a 1500 ms, padrão 300),
  o volume no alto-falante e a força no tato, ao lado das duas chaves e do intervalo. A duração vale
  no tato e no alto-falante. O universal e a receita do Minecraft Dungeons II leem os três; no
  padrão, o susto é o de antes.
- A tela do jogo só se lê quando você pede: o botão «Ver a tela», na aba Sentidos, começa a leitura,
  e «Parar de ver» (ou clicar de novo, ou fechar o jogo) a encerra. A chave «Tela» saiu, e quem a
  tinha ligada volta com ela desligada. Num Hefesto que ainda não lê a tela no clique, o «Agora»
  diz «Tela: Este Hefesto não lê» e nada mais acontece.
- Aba nova, «Controles»: cada controle, pela cor do plástico, tem a Força e o Volume dele, lado a
  lado. Os dois valem juntos e vezes a Força geral: a Força de um controle não mexe no volume do
  alto-falante dele, e o Volume não mexe na vibração.
- O diário da extensão ganha um resumo por minuto de jogo: em cada controle, o que tocou em cada
  canal e o que não tocou, com o motivo (o Modo Nativo, o jogo mais forte, o rádio sem vaga para o
  som). Minuto sem jogo não escreve nada.

## 0.4.21 (02/11/2026)

- O coração e o susto voltam a tocar na vibração fina: a extensão registra os padrões dela no
  Hefesto (`haptica.registrar`) antes do primeiro toque, e de novo quando o Hefesto os perde (o
  daemon reiniciou). Até a 0.4.20, todo toque era recusado com «padrão não registrado».

## 0.4.9 a 0.4.20 (02/11/2026)

- A memória do jogo tem uma chave só, a «Memória neste jogo» do Hefesto, na aba Geral: o
  `jogo.memoria` chega ao motor só com ela ligada, em toda receita. A chave «Memória» própria da
  receita da comunidade e o `memoria.json` saem; a receita da comunidade que lê a memória diz isso
  na página e espera a chave.
- A coluna «Agora» ganha linhas: os sentidos lendo agora, a memória que espera a chave e o último
  efeito tocado, com a hora.
- Na aba Efeitos, cada linha só aparece quando a receita que vale tem o efeito dela: no Minecraft
  Dungeons II, o «Alívio» some. A «Cor do dano» segue pedindo a «Luz do dano» ligada.
- O manifesto pede as permissões que o Hefesto já aceita: o som do jogo, o nível do microfone, a
  tela do jogo, a identidade do jogo, a memória do jogo, a vibração fina, o alto-falante e as luzes
  de jogador. Na atualização, o Hefesto desliga a extensão até o novo aceite. Com elas, o coração,
  o susto e o lado do universal voltam a tocar. A tela do jogo só se lê com o sentido «Tela» ligado.
- A janela tem as abas do desenho: Geral (Procurar receitas, Força, Receita, O golpe vai para),
  Sentidos, Efeitos (coração, alívio, golpe com lado, lado na luz, luz do dano, susto no
  alto-falante e no tato, impacto nos gatilhos, clima tenso e peso da mira), Canais e «Ensinar
  este jogo», a página do Estúdio. Cada ajuste vale no tique seguinte, em toda receita; no padrão,
  a extensão escreve o mesmo de antes.
- A receita do Minecraft Dungeons II lê a aba Efeitos como o universal: o coração, o golpe com
  lado, a luz do dano, os dois sustos, o impacto nos gatilhos e o clima tenso mudam o que ela
  escreve; no padrão, ela escreve o mesmo de antes.
- A receita ensinada pela tela no Estúdio liga o sentido «Tela» e passa a ler a tela do jogo na
  hora; a receita ensinada pelo som liga o sentido «Som do jogo». Desligar a chave depois cala a
  receita, como antes.
- Na aba Geral, cada controle conectado ganha um cartão com a chave «Sente os efeitos»; o desligado
  não recebe nada, e a escolha sobrevive ao reinício. O «Nível» da coluna «Agora» mostra o clima
  da cena ao vivo.
- A cor do dano e o intervalo do susto se ajustam na aba Efeitos; no padrão (vermelho e 5 s), a
  extensão escreve o mesmo de antes.
- O Modo imersão pesa a mira pela receita: no universal e no Minecraft Dungeons II, o perigo e o
  dano recente deixam o giroscópio de 1 a 0,6, e o alívio o devolve. O «Peso da mira» da aba
  Efeitos nasce ligado, e o manifesto pede `escrever:mira`; o jogo que recusa o peso o cala por
  5 s, ou até o jogo trocar, sem derrubar a extensão.
- No FAÇA do Estúdio, a dica do efeito diz a entrada pelo nome e pelo valor de agora («pinta a luz
  de «Cor do dano» (#ff0000)»), e não pelo `$cor_do_dano` cru.

## 0.4.8 (02/11/2026)

- A receita da comunidade que sai do índice assinado sai do disco; sem internet, a baixada fica, e
  a tela não vê o erro cru. O «Tocar» avisa a página quando a linha acaba. Na página, o erro sai
  numa linha laranja sem trocar de vista, e o que deu certo não se narra.
- A procura da comunidade roda num fio que não segura a saída: com a rede lenta, a extensão
  para na hora em que o Hefesto pede. O pedido do Estúdio que a porta recusa para a caça e
  responde à página, e a extensão segue ouvindo o jogo.

## 0.4.7 (02/11/2026)


## 0.4.6 (02/11/2026)

- As receitas da comunidade (`comunidade.py`) moram no repositório `hefesto-receitas-imersao`, em
  `steam/<chave>/<nome>.json`, com um `indice.json` assinado (Ed25519 no formato do minisign; a
  chave pública vem na extensão, e a conferência é Python puro). O índice se baixa uma vez por dia,
  ou no «Procurar receitas» da página, e só vale com a assinatura certa; a receita do jogo aberto
  se baixa depois, tem de bater com a soma SHA-256 do índice e passa de novo pelo validador. A
  receita que lê a memória chega com a chave «Memória» dela desligada, e no jogo com anticheat
  ligá-la passa pelo aviso. A sua e a estudada vencem a da comunidade, e a página diz de onde
  veio a que vale. O manifesto passa de `rede:nenhuma` a `rede:internet`.

## 0.4.5 (02/11/2026)


## 0.4.4 (02/11/2026)

- O Estúdio desenha a receita como grafo (`estudio/grafo.py`): sentido, derivado, estado, regra e
  efeito em colunas, com até 64 nós e 32 regras. O ciclo, o nó órfão e a aresta de tipo errado (a
  regra que faz um estado, a expressão que lê um efeito) se recusam com o nó apontado. A vista
  «Texto» mostra a receita em JSON, validada a cada tecla; «Exportar» a copia e «Importar» grava só
  o texto sem erro, que vale no tique seguinte.

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
