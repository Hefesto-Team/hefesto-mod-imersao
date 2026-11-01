# Decisões

Uma linha por decisão de produto tomada na implementação, por delegação, a validar.

- 01/11/2026 · O processo usa só a biblioteca padrão, sem pydantic: o Hefesto o sobe com `python3 -I`, que não enxerga a `.venv` de ninguém. O validador é um mini-esquema próprio (`receita/formato.py`), com o `extra="forbid"` no mesmo lugar da régua. Por delegação, a validar.
- 01/11/2026 · O JSON da receita se lê por um analisador próprio (`receita/json_com_linhas.py`) que guarda a linha de cada chave e recusa a chave repetida: o `json` da biblioteca padrão não dá a linha e deixa a repetida passar calada. Por delegação, a validar.
- 01/11/2026 · O formato 1 deixa de fora `id`, `versao`, `autoria`, `muda_em` e `lado_de`: entram num formato novo quando houver quem os leia. Por delegação, a validar.
- 01/11/2026 · No mesmo canal do mesmo controle vence a maior força; na força igual, a maior `prioridade`; depois, a regra que disparou por último. Por delegação, a validar.
- 01/11/2026 · O zero que solta um canal passa por cima do teto do tato vivo: soltar nunca espera. Por delegação, a validar.
- 01/11/2026 · A luz não se solta ao fim do efeito nem ao parar: a porta não diz qual era a luz de antes, e devolvê-la é do Hefesto. Por delegação, a validar.
- 01/11/2026 · `haptica.tocar` e `som.tocar` são os nomes provisórios até a porta os ter; quando ela responde «método desconhecido», a háptica cai no motor pelo envelope do padrão e o som se cala. Por delegação, a validar.
- 01/11/2026 · Um efeito «enquanto» dura pelo menos 250 ms, para o estado que pisca não virar zumbido. Por delegação, a validar.
- 01/11/2026 · A frequência 0 no gatilho recusa e aponta o modo `desliga`: o console a lê como desligado, e a receita diz o que o controle faz. Por delegação, a validar.
- 01/11/2026 · A receita pode ler um tópico que a porta ainda não entrega: o processo não o assina, o diário diz qual é, e o sentido dele fica parado até a porta o ter. Por delegação, a validar.
