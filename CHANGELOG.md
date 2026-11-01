# Mudanças

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
