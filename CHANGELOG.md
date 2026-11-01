# Mudanças

## 0.3.0 (01/11/2026)

- O motor lê o caminho do controle do jogo ao vivo (`motor/caminho.py`): por controle e por canal
  (motor, háptica, gatilho e luz), o que o jogo escreveu nos últimos 3 s. No canal ocupado, a
  receita só sai mais forte que o jogo; no livre, sai inteira. Vale de P1 a P4, no cabo e no rádio.
- A luz do jogo, que não tem tópico, se aprende pela recusa `-32011` da porta (com `data.vence` em
  `jogo`, ou sem `data`); a recusa que outra extensão vence não conta, e a escrita recusada não se
  repete enquanto o mesmo valor continuar pedido.
- A máscara Xbox ou Nintendo de `jogo.identidade` deixa a luz e o gatilho da receita inteiros
  desde o começo; o tópico entra na assinatura quando a porta o entregar.
- O rumble do jogo sem a batida de 250 ms por 600 ms vale zero, e o `jogo.fechou` solta tudo.
- Sem `haptica.tocar` na porta, o padrão que cai no motor disputa com o motor do jogo.

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
