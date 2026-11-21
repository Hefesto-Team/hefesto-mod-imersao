"""A saída pela porta das modificações: só o que muda, renovado a tempo e sob o teto do tato vivo.

Cada tique recebe o vencedor de cada vaga e escreve a diferença: ``vibracao.set`` (o motor
esquerdo é o ``forte``, o direito o ``fraco``, e o par se renova antes dos 3 s da porta),
``gatilho.set`` com os nomes do ``trigger.set``, ``luz.set``, ``haptica.tocar``, ``som.tocar`` (o
som da caixa pelo id, ou o recorte do estalo do jogo pelo ``t`` do ``jogo.som``) e ``leds.set``
(as luzes de jogador por máscara e prazo) e ``mira.peso`` (o ganho do giroscópio, com prazo, renovado
enquanto o efeito vale e fora do teto, que é do tato). O teto é o do tato vivo, 12 escritas por segundo em
cada controle e 40 no total: o que passa espera o tique seguinte, e o valor mais novo é o que sai.
Quando a porta não conhece ``haptica.tocar``, o padrão cai no motor, pelo envelope, e quem pediu
o mede de novo contra o motor do jogo (``pelo_motor``); quando não
conhece ``som.tocar`` ou ``leds.set``, aquele efeito se cala. A escrita que a porta recusa com
``-32011`` (mais fraca que o pedido vivo no canal) não ficou escrita: ela vai a quem a pediu, o
mesmo valor não se repete enquanto continuar pedido, e a conta volta ao que a porta aceitou antes,
que segue no controle e recebe o zero quando o canal se solta ou a extensão sai. O ``mira.peso``
recusado com ``-32013`` (o jogo de anticheat sem a chave) vai a quem o pediu e não se repete, e a
porta que não o conhece (ou não deu a permissão) cala o peso da mira.

O teto da porta, ``-32014``, não deixa a escrita registrada: o pedido volta ao que havia, entra nos
adiados e se tenta de novo no tique em que a conta da extensão diz que cabe; o motivo é «teto», dito
ao fim do efeito que nunca coube. O som e as luzes de jogador só contam como tocados com a escrita
aceita. As outras recusas sem tratamento (sem permissão, sem ponte) se tentam de novo só no prazo
de :data:`RENOVA_MS`, nunca por tique, e a linha do diário sai uma vez por efeito e por motivo. Tudo
isso vale por controle: a conta é da identidade do controle, no cabo e no rádio.

O ``luz.set`` e o ``gatilho.set`` de um efeito com ``dura_ms`` levam ``ate_ms``, o que resta do
efeito quando a escrita sai: a porta devolve o que havia quando o prazo vence, sem depender da
extensão viva. A entrada da luz sai da conta quando o efeito acaba, e o mesmo pedido que vier depois
se escreve de novo. A porta que devolve diz ``devolve: true`` na resposta ao pedido com prazo, e
para esse controle o ``Off`` do fim do gatilho não se escreve; a que não diz recebe o ``Off`` de
sempre.

Um pedido vivo que só anda nos parâmetros contínuos (força, batimento, brilho) só se reescreve
quando a mudança se sente: um degrau de :data:`DEGRAUS` desde o que está no controle, no máximo uma
vez por :data:`INTERVALO_DO_DEGRAU_MS` em cada canal e controle, e só com :data:`VAGA_DO_EVENTO`
escritas ainda livres no teto. O efeito novo, o zero e a passagem por zero saem no tique deles.
A batida do padrão que se repete, desenhada no motor pelo envelope, conta no teto: só liga com
:data:`VAGA_DO_EVENTO` escritas livres e mais a do zero que a encerra, e a que não cabe se adia,
nunca o evento.

O Som no corpo e os Gatilhos que vibram vão pelo ``corpo.ligar`` (:meth:`Saida.ligar_o_corpo`), um
pedido por controle com o prazo :data:`ATE_MS_DO_CORPO`, renovado a cada :data:`RENOVA_MS` e no
tique em que muda; o controle que sai do pedido recebe o vazio, que o solta. A recusa vai a quem
pediu e se tenta de novo no prazo da renovação; a porta que não conhece o pedido, ou que não deu a
permissão ``escrever:corpo``, cala os dois.
"""
from __future__ import annotations

import asyncio
import contextlib
import re
from collections import Counter, deque
from collections.abc import Awaitable, Callable
from typing import Any

from efeitos import peso_da_mira
from motor import efeitos as catalogo
from motor.arbitragem import Pedido, Vaga

TETO_POR_CONTROLE = 12
TETO_TOTAL = 40
JANELA_MS = 1000.0
RENOVA_MS = 2500.0
ATE_MS_DA_HAPTICA = 3000
METODO_DESCONHECIDO = -32601
MAIS_FRACO = -32011
NAO_REGISTRADO = "padrão não registrado"
SEM_PERMISSAO = -32010
NAO_ESCREVEU = -32013
DEGRAUS = {"forca": 0.05, "bpm": 4.0, "brilho": 0.05}
INTERVALO_DO_DEGRAU_MS = 250.0
VAGA_DO_EVENTO = 4
SEM_PONTE = -32015
TETO_CHEIO = -32014
MOTIVOS_POR_CODIGO = {MAIS_FRACO: "cedeu", SEM_PONTE: "sem_ponte", SEM_PERMISSAO: "sem_permissao",
                      NAO_ESCREVEU: "anticheat", METODO_DESCONHECIDO: "porta_sem_o_pedido",
                      TETO_CHEIO: "teto"}
MOTIVO_DA_PORTA = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
MODOS_QUE_CALAM = ("nativo", "steam_input")
ATE_MS_DO_CORPO = 5000
CANAL_DO_CORPO = "corpo"
PARTES_DO_CORPO = (("som_no_corpo", "som no corpo"), ("gatilhos", "gatilhos que vibram"))

Pedir = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]
Chave = tuple[str, str, str]
Recusado = Callable[[Chave, dict[str, Any], Any], None]
Vencedores = dict[Vaga, Pedido]


def motivo_da_recusa(codigo: Any, dados: Any) -> str:
    """Por que a porta não escreveu, numa palavra: o ``motivo`` que ela devolve, o Modo Nativo, a
    outra extensão mais forte ou o código do erro."""
    if isinstance(dados, dict):
        motivo = dados.get("motivo")
        if isinstance(motivo, str) and MOTIVO_DA_PORTA.match(motivo):
            return motivo
        modo = dados.get("modo")
        if modo in MODOS_QUE_CALAM:
            return str(modo)
        vence = dados.get("vence")
        if isinstance(vence, str) and vence.startswith("extensao"):
            return "outra_extensao"
    if isinstance(codigo, int) and not isinstance(codigo, bool):
        return MOTIVOS_POR_CODIGO.get(codigo, f"recusa_{abs(codigo)}")
    return "recusa"


class Saida:
    """O que já foi escrito em cada controle, e a conta do teto."""

    def __init__(self, pedir: Pedir, diario: Callable[[str], None] | None = None,
                 recusado: Recusado | None = None,
                 pelo_motor: Callable[[Vencedores], Vencedores] | None = None) -> None:
        self._pedir = pedir
        self._diario = diario or (lambda _frase: None)
        self._recusado = recusado or (lambda _chave, _params, _dados: None)
        self._pelo_motor = pelo_motor or (lambda vencedores: vencedores)
        self.recusados: dict[Chave, dict[str, Any]] = {}
        self.recusas_do_tique: list[tuple[str, str, str]] = []
        self.aceitas_do_tique: list[tuple[str, str]] = []
        self.frases_do_tique: list[tuple[str, str, str]] = []
        self.adiadas_do_tique: list[tuple[str, str]] = []
        self.escrito: dict[Chave, tuple[float, dict[str, Any]]] = {}
        self.janela: deque[tuple[float, str]] = deque()
        self.sem_haptica = False
        self.sem_som = False
        self.sem_leds = False
        self.sem_mira = False
        self._registrados = False
        self._formas: dict[str, float | None] = {}
        self._registradas: dict[str, float | None] = {}
        self._tocados: set[tuple[str, str, float]] = set()
        self._vivos: dict[Vaga, tuple[tuple[str, float, int], dict[str, float]]] = {}
        self._degrau_em: dict[tuple[str, str], float] = {}
        self._no_tique: tuple[float, list[tuple[str, str]]] = (-1.0, [])
        self._no_motor: dict[str, frozenset[tuple[Any, ...]]] = {}
        self._motor_em_dia: dict[str, frozenset[tuple[Any, ...]]] = {}
        self.sem_corpo = False
        self.corpos: dict[str, tuple[float, dict[str, Any], bool]] = {}
        self.corpos_do_tique: list[tuple[str, str]] = []
        self.pedidos_do_corpo: Callable[[], dict[str, dict[str, Any]]] | None = None
        self._no_teto: set[Chave] = set()
        self._falhou: set[Chave] = set()
        self._ditas: set[tuple[Chave, str, Any]] = set()
        self._quem: dict[Chave, frozenset[tuple[str, float]]] = {}
        self._fins: dict[Chave, float] = {}
        self._devolve: dict[Chave, bool] = {}

    def _cabe(self, t_ms: float, uniq: str, reserva: int = 0,
              reserva_total: int | None = None) -> bool:
        while self.janela and t_ms - self.janela[0][0] >= JANELA_MS:
            self.janela.popleft()
        no_controle = sum(1 for _, u in self.janela if u == uniq)
        total = reserva if reserva_total is None else reserva_total
        return (len(self.janela) < TETO_TOTAL - total
                and no_controle < TETO_POR_CONTROLE - reserva)

    @staticmethod
    def _sente(nome: str, antes: float, agora: float) -> bool:
        return (antes == 0) != (agora == 0) or abs(agora - antes) >= DEGRAUS[nome] - 1e-9

    def _no_degrau(self, t_ms: float, vaga: Vaga, pedido: Pedido, irmaos: int = 1
                   ) -> dict[str, Any]:
        identidade = (pedido.efeito, pedido.inicio_ms, pedido.regra)
        novos = {k: float(pedido.params[k]) for k in DEGRAUS if k in pedido.params}
        vivo = self._vivos.get(vaga)
        if vivo is not None and vivo[0] == identidade:
            aceitos = vivo[1]
            if not any(self._sente(k, aceitos[k], v) for k, v in novos.items()):
                return {**pedido.params, **aceitos}
            uniq, canal, _ = vaga
            ultimo = self._degrau_em.get((uniq, canal))
            passagem = any((aceitos[k] == 0) != (v == 0) for k, v in novos.items())
            cedo = ultimo is not None and ultimo != t_ms and t_ms - ultimo < INTERVALO_DO_DEGRAU_MS
            if self._no_tique[0] != t_ms:
                self._no_tique = (t_ms, [])
            agora = self._no_tique[1]
            junto = (uniq, canal) in agora
            reserva = VAGA_DO_EVENTO + irmaos - 1
            cabe = self._cabe(t_ms, uniq, reserva + sum(1 for u, _ in agora if u == uniq),
                              reserva + len(agora))
            if not passagem and not junto and (cedo or not cabe):
                return {**pedido.params, **aceitos}
            agora.append((uniq, canal))
        self._degrau_em[(vaga[0], vaga[1])] = t_ms
        self._vivos[vaga] = (identidade, novos)
        return pedido.params

    async def _escrever(self, t_ms: float, chave: Chave, metodo: str,
                        params: dict[str, Any], zero: bool = False, reserva: int = 0,
                        fim_ms: float | None = None) -> bool:
        uniq = chave[0]
        passa_do_teto = zero and chave not in self._no_teto
        if not passa_do_teto and not self._cabe(t_ms, uniq, reserva):
            self.adiadas_do_tique.append((uniq, chave[1]))
            return False
        self.janela.append((t_ms, uniq))
        antes = self.escrito.get(chave)
        self.escrito[chave] = (t_ms, params)
        enviado = params if fim_ms is None else {**params, "ate_ms": max(1, round(fim_ms - t_ms))}
        try:
            resposta = await self._pedir(metodo, enviado)
        except (RuntimeError, OSError, asyncio.TimeoutError) as exc:
            codigo = getattr(exc, "codigo", None)  # (noqa-acento)
            dados = getattr(exc, "dados", None)
            if codigo == TETO_CHEIO:
                self._desfazer(chave, antes)
                self._no_teto.add(chave)
                self.adiadas_do_tique.append((uniq, chave[1]))
                return False
            if not (metodo == "haptica.tocar" and (codigo == METODO_DESCONHECIDO
                                                   or NAO_REGISTRADO in str(exc))):
                self._anotar_a_recusa(chave, codigo, dados, str(exc))
            if codigo == MAIS_FRACO:
                self._desfazer(chave, antes)
                self.recusados[chave] = params
                self._recusado(chave, params, dados)
                return True
            if codigo == METODO_DESCONHECIDO and metodo == "haptica.tocar":
                self.sem_haptica = True
                self._diario("a porta não toca háptica: o padrão segue pelo motor")
                self._desfazer(chave, antes)
                return False
            if metodo == "haptica.tocar" and NAO_REGISTRADO in str(exc):
                self._registrados = False
                self._desfazer(chave, antes)
                return True
            if codigo == METODO_DESCONHECIDO and metodo == "som.tocar":
                self.sem_som = True
                self._diario("a porta não toca som: o efeito de som fica calado")
                return False
            if codigo == METODO_DESCONHECIDO and metodo == "leds.set":
                self.sem_leds = True
                self._diario("a porta não acende as luzes de jogador: o lado na luz fica calado")
                return False
            self._falhou.add(chave)
            self._devolve.pop(chave, None)
            self._dizer(chave, f"{metodo} recusado: {exc}", motivo_da_recusa(codigo, dados))
        else:
            self._no_teto.discard(chave)
            self._falhou.discard(chave)
            self._ditas = {d for d in self._ditas if d[0] != chave}
            self._devolve[chave] = fim_ms is not None and isinstance(resposta, dict) and (
                resposta.get("devolve") is True)
            if not zero:
                self.aceitas_do_tique.append((uniq, chave[1]))
        return True

    def _dizer(self, chave: Chave, frase: str, motivo: str) -> None:
        """A linha da recusa vai ao diário uma vez por efeito e por motivo, não a cada tentativa."""
        marca = (chave, motivo, self._quem.get(chave))
        if marca not in self._ditas:
            self._ditas.add(marca)
            self._diario(frase)

    def _anotar_a_recusa(self, chave: Chave, codigo: Any, dados: Any, frase: str = "") -> None:
        self.recusas_do_tique.append((chave[0], chave[1], motivo_da_recusa(codigo, dados)))
        if frase:
            self.frases_do_tique.append((chave[0], chave[1], frase))

    def tirar_os_desfechos(self) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]],
                                          list[tuple[str, str]]]:
        """As escritas que a porta aceitou desde a última chamada, ``(uniq, canal da escrita)``,
        as recusadas com a frase dela, ``(uniq, canal da escrita, frase)``, e as que o teto da
        extensão adiou, ``(uniq, canal da escrita)``."""
        aceitas, self.aceitas_do_tique = self.aceitas_do_tique, []
        frases, self.frases_do_tique = self.frases_do_tique, []
        adiadas, self.adiadas_do_tique = self.adiadas_do_tique, []
        return aceitas, frases, adiadas

    def tirar_os_corpos(self) -> list[tuple[str, str]]:
        """Os pedidos do corpo que a porta aceitou desde a última chamada: ``(uniq, parte)``."""
        corpos, self.corpos_do_tique = self.corpos_do_tique, []
        return corpos

    async def ligar_o_corpo(self, t_ms: float, desejados: dict[str, dict[str, Any]]) -> None:
        """O ``corpo.ligar`` de cada controle em ``desejados`` (``{uniq: {som_no_corpo?,
        gatilhos?}}``) que mudou ou vence a renovação, e o vazio no que saiu do pedido."""
        if self.sem_corpo:
            return
        querem = {uniq for uniq, pedido in desejados.items() if pedido}
        for uniq in sorted(set(self.corpos) - querem):
            _t, _pedido, aceito = self.corpos.pop(uniq)
            if aceito:
                self.janela.append((t_ms, uniq))
                with contextlib.suppress(RuntimeError, OSError, asyncio.TimeoutError):
                    await self._pedir("corpo.ligar", {"uniq": uniq, "ate_ms": ATE_MS_DO_CORPO})
        for uniq in sorted(querem):
            pedido = desejados[uniq]
            antes = self.corpos.get(uniq)
            if antes is not None and antes[1] == pedido and t_ms - antes[0] < RENOVA_MS:
                continue
            if not self._cabe(t_ms, uniq):
                continue
            self.janela.append((t_ms, uniq))
            try:
                await self._pedir("corpo.ligar", {"uniq": uniq, **pedido,
                                                  "ate_ms": ATE_MS_DO_CORPO})
            except (RuntimeError, OSError, asyncio.TimeoutError) as exc:
                codigo = getattr(exc, "codigo", None)  # (noqa-acento)
                if codigo in (METODO_DESCONHECIDO, SEM_PERMISSAO):
                    self.sem_corpo = True
                    self.corpos.clear()
                    self._diario(f"a porta não liga o corpo ({exc}): o Som no corpo e os "
                                 "Gatilhos que vibram ficam calados")
                    return
                self.corpos[uniq] = (t_ms, pedido, False)
                self.recusas_do_tique.append((uniq, CANAL_DO_CORPO, "nao_escreveu" if (
                    codigo == NAO_ESCREVEU) else motivo_da_recusa(codigo, getattr(exc, "dados", None))))
                continue
            self.corpos[uniq] = (t_ms, pedido, True)
            self.corpos_do_tique.extend((uniq, nome) for parte, nome in PARTES_DO_CORPO
                                        if parte in pedido)

    def tirar_as_recusas(self) -> list[tuple[str, str, str]]:
        """As recusas da porta desde a última chamada: ``(uniq, canal da escrita, motivo)``."""
        recusas, self.recusas_do_tique = self.recusas_do_tique, []
        return recusas

    def _desfazer(self, chave: Chave, antes: tuple[float, dict[str, Any]] | None) -> None:
        if antes is None:
            self.escrito.pop(chave, None)
        else:
            self.escrito[chave] = antes

    def _desejado(self, t_ms: float, vencedores: dict[Vaga, Pedido]
                  ) -> dict[Chave, tuple[str, dict[str, Any], bool]]:
        desejo: dict[Chave, tuple[str, dict[str, Any], bool]] = {}
        motores: dict[str, dict[str, float]] = {}
        no_motor: dict[str, set[tuple[Any, ...]]] = {}
        quem: dict[Chave, set[tuple[str, float]]] = {}
        self._fins = {}
        self._vivos = {vaga: vivo for vaga, vivo in self._vivos.items() if vaga in vencedores}
        grupos = Counter((uniq, canal) for uniq, canal, _ in vencedores)
        for (uniq, canal, lado), pedido in sorted(vencedores.items()):
            p = self._no_degrau(t_ms, (uniq, canal, lado), pedido, grupos[(uniq, canal)])
            na_chave = "vibracao" if canal == "motor" or (
                canal == "haptica" and self.sem_haptica) else canal
            quem.setdefault((uniq, na_chave, lado if na_chave in ("haptica", "gatilho") else "-"),
                            set()).add((pedido.efeito, pedido.inicio_ms))
            if canal == "motor" or (canal == "haptica" and self.sem_haptica):
                forca = p["forca"]
                marca: tuple[Any, ...] = (canal, lado, pedido.efeito, pedido.inicio_ms,
                                          pedido.regra, forca)
                if "padrao" in p:  # (noqa-acento)
                    envelope = catalogo.envelope(p["padrao"], t_ms - p["inicio_ms"], p["bpm"],  # (noqa-acento)
                                                 p.get("escala_ms"))
                    forca *= envelope
                    repete = catalogo.PADROES[p["padrao"]].repete  # (noqa-acento)
                    marca += (p["bpm"],) if repete else (envelope,)
                no_motor.setdefault(uniq, set()).add(marca)
                atual = motores.setdefault(uniq, {"esquerdo": 0.0, "direito": 0.0})
                atual[lado] = max(atual[lado], forca)
            elif canal == "haptica":
                self._formas[p["padrao"]] = p.get("escala_ms")  # (noqa-acento)
                desejo[(uniq, "haptica", lado)] = ("haptica.tocar", {
                    "uniq": uniq, "id": p["padrao"], "forca": round(p["forca"], 3),  # (noqa-acento)
                    "bpm": round(p["bpm"]), "lado": lado, "ate_ms": ATE_MS_DA_HAPTICA}, False)
            elif canal == "gatilho":
                nome, valores = p["trigger"]
                desejo[(uniq, "gatilho", lado)] = ("gatilho.set", {
                    "uniq": uniq, "lado": lado, "modo": nome, "params": valores}, False)
                if "fim_ms" in p:
                    self._fins[(uniq, "gatilho", lado)] = p["fim_ms"]
            elif canal == "luz":
                desejo[(uniq, "luz", "-")] = ("luz.set", {
                    "uniq": uniq, "rgb": p["rgb"], "brilho": p["brilho"]}, False)
                if "fim_ms" in p:
                    self._fins[(uniq, "luz", "-")] = p["fim_ms"]
            elif canal == "som":
                som = {"uniq": uniq, "som": p["som"], "volume": p["volume"]}
                for campo in ("t", "dura_s"):
                    if campo in p:
                        som[campo] = p[campo]
                desejo[(uniq, "som", "-")] = ("som.tocar", {**som, "inicio_ms": p["inicio_ms"]},
                                              False)
            elif canal == "mira":
                desejo[(uniq, "mira", "-")] = ("mira.peso",
                                               peso_da_mira.pedido(uniq, p["ganho"]), False)
            elif canal == "leds":
                desejo[(uniq, "leds", "-")] = ("leds.set", {
                    "uniq": uniq, "mascara": p["mascara"], "ate_ms": p["ate_ms"],
                    "inicio_ms": p["inicio_ms"]}, False)
        for uniq, lados in motores.items():
            forte, fraco = round(lados["esquerdo"] * 255), round(lados["direito"] * 255)
            if forte or fraco:
                desejo[(uniq, "vibracao", "-")] = ("vibracao.set", {
                    "uniq": uniq, "fraco": fraco, "forte": forte}, False)
        for chave, (_, params) in self.escrito.items():
            if chave in desejo:
                continue
            uniq, canal, lado = chave
            if canal == "vibracao" and (params["fraco"] or params["forte"]):
                desejo[chave] = ("vibracao.set", {"uniq": uniq, "fraco": 0, "forte": 0}, True)
            elif canal == "gatilho" and params["modo"] != "Off" and not self._devolve.get(chave):
                desejo[chave] = ("gatilho.set", {"uniq": uniq, "lado": lado, "modo": "Off",
                                                 "params": []}, True)
            elif canal == "haptica" and params["forca"]:
                desejo[chave] = ("haptica.tocar", {**params, "forca": 0.0, "ate_ms": 0}, True)
        self._no_motor = {uniq: frozenset(marcas) for uniq, marcas in no_motor.items()}
        self._quem = {chave: frozenset(quem_pediu) for chave, quem_pediu in quem.items()}
        return desejo

    def _batida(self, chave: Chave, antes: tuple[float, dict[str, Any]] | None,
                params: dict[str, Any]) -> bool:
        marca = self._no_motor.get(chave[0])
        return (chave[1] == "vibracao" and marca is not None and antes is not None
                and antes[1] != params and self._motor_em_dia.get(chave[0]) == marca)

    def _em_dia(self, chave: Chave) -> None:
        if chave[1] == "vibracao" and chave[0] in self._no_motor:
            self._motor_em_dia[chave[0]] = self._no_motor[chave[0]]

    async def aplicar(self, t_ms: float, vencedores: dict[Vaga, Pedido]) -> None:
        """Escreve o que mudou desde o tique anterior, sob o teto."""
        desejo = self._desejado(t_ms, vencedores)
        self.recusados = {chave: params for chave, params in self.recusados.items()
                          if chave in desejo and self._sem_marca(desejo[chave][1]) == params}
        if self.sem_haptica is False and any(m == "haptica.tocar" for m, _, _ in desejo.values()):
            for chave in sorted(desejo):
                metodo, params, zero = desejo[chave]
                if metodo == "haptica.tocar" and not await self._tocar(t_ms, chave, params, zero):
                    break
            if self.sem_haptica:
                desejo = self._desejado(t_ms, self._pelo_motor(vencedores))
        vivos: set[tuple[str, str, float]] = set()
        for chave in [c for c in self.escrito if c not in desejo and (
                c[1] in ("mira", "luz") or (c[1] == "gatilho" and self._devolve.get(c)))]:
            del self.escrito[chave]
        for chave in sorted(desejo):
            metodo, params, zero = desejo[chave]
            if metodo == "haptica.tocar":
                continue
            if metodo == "mira.peso":
                if not self.sem_mira:
                    await self._pesar(t_ms, chave, params)
                continue
            if metodo in ("som.tocar", "leds.set"):
                marca = (chave[0], metodo, params.pop("inicio_ms"))
                vivos.add(marca)
                calado = self.sem_som if metodo == "som.tocar" else self.sem_leds
                if calado or marca in self._tocados:
                    continue
                tentou = self.escrito.get(chave)
                if (chave in self._falhou and tentou is not None
                        and t_ms - tentou[0] < RENOVA_MS):
                    continue
                if await self._escrever(t_ms, chave, metodo, params) and (
                        chave not in self._falhou):
                    self._tocados.add(marca)
                continue
            if self.recusados.get(chave) == params:
                continue
            antes = self.escrito.get(chave)
            vence = (metodo == "vibracao.set" or chave in self._falhou) and (
                antes is not None and not zero and t_ms - antes[0] >= RENOVA_MS)
            if antes is not None and antes[1] == params and not vence:
                self._em_dia(chave)
                continue
            batida = self._batida(chave, antes, params)
            liga = batida and bool(params["forte"] or params["fraco"])
            reserva = VAGA_DO_EVENTO + 1 if liga else 0
            if await self._escrever(t_ms, chave, metodo, params, zero and not batida, reserva,
                                    self._fins.get(chave)):
                self._em_dia(chave)
        for uniq in self._no_motor:
            if (uniq, "vibracao", "-") not in desejo:
                self._em_dia((uniq, "vibracao", "-"))
        self._motor_em_dia = {uniq: marca for uniq, marca in self._motor_em_dia.items()
                              if uniq in self._no_motor}
        for chave in sorted(self._no_teto - desejo.keys()):
            self._no_teto.discard(chave)
            self.recusas_do_tique.append((chave[0], chave[1], motivo_da_recusa(TETO_CHEIO, None)))
        self._falhou &= desejo.keys()
        self._ditas = {d for d in self._ditas if d[0] in desejo}
        self._devolve = {c: v for c, v in self._devolve.items() if c in self.escrito}
        self._tocados &= vivos
        if self.pedidos_do_corpo is not None:
            await self.ligar_o_corpo(t_ms, self.pedidos_do_corpo())

    @staticmethod
    def _sem_marca(params: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in params.items() if k != "inicio_ms"}

    async def _tocar(self, t_ms: float, chave: Chave, params: dict[str, Any], zero: bool) -> bool:
        if self.recusados.get(chave) == params:
            return True
        antes = self.escrito.get(chave)
        vence = antes is not None and not zero and t_ms - antes[0] >= RENOVA_MS
        if antes is not None and antes[1] == params and not vence:
            return True
        if not self._registrados and not await self._registrar():
            return not self.sem_haptica
        nome = params["id"]
        if (self._formas.get(nome) != self._registradas.get(nome)
                and not await self._registrar_um(nome, self._formas.get(nome))):
            return not self.sem_haptica
        await self._escrever(t_ms, chave, "haptica.tocar", params, zero)
        return not self.sem_haptica

    async def _registrar(self) -> bool:
        """Registra o catálogo na porta antes do primeiro toque e depois de ela o perder; o padrão
        que não se repete vai na duração pedida agora."""
        self._registradas = {}
        for nome in catalogo.PADROES:
            if not await self._registrar_um(nome, self._formas.get(nome)):
                return False
        self._registrados = True
        return True

    async def _registrar_um(self, nome: str, escala_ms: float | None) -> bool:
        """O padrão ``nome`` na duração ``escala_ms``: o mesmo ``id`` registrado de novo troca os
        golpes dele na porta."""
        escolhido = catalogo.padrao(nome, escala_ms)
        try:
            await self._pedir("haptica.registrar", {"id": nome, "golpes": catalogo.golpes(escolhido),
                                                    "repete": escolhido.repete})
        except (RuntimeError, OSError, asyncio.TimeoutError) as exc:
            self.sem_haptica = True
            if getattr(exc, "codigo", None) == METODO_DESCONHECIDO:
                self._diario("a porta não toca háptica: o padrão segue pelo motor")
            else:
                self._diario(f"haptica.registrar recusado ({exc}): o padrão segue pelo motor")
            return False
        self._registradas[nome] = escala_ms
        return True

    async def _pesar(self, t_ms: float, chave: Chave, params: dict[str, Any]) -> None:
        if self.recusados.get(chave) == params:
            return
        antes = self.escrito.get(chave)
        if antes is not None and antes[1] == params and t_ms - antes[0] < peso_da_mira.RENOVA_MS:
            return
        self.escrito[chave] = (t_ms, params)
        try:
            await self._pedir("mira.peso", params)
        except (RuntimeError, OSError, asyncio.TimeoutError) as exc:
            codigo = getattr(exc, "codigo", None)  # (noqa-acento)
            self._anotar_a_recusa(chave, codigo, getattr(exc, "dados", None))
            if codigo == NAO_ESCREVEU:
                self._desfazer(chave, antes)
                self.recusados[chave] = params
                self._recusado(chave, params, getattr(exc, "dados", None))
            elif codigo in (METODO_DESCONHECIDO, SEM_PERMISSAO):
                self.sem_mira = True
                self._desfazer(chave, antes)
                self._diario("a porta não pesa a mira: o peso da mira fica calado")
            else:
                self._dizer(chave, f"mira.peso recusado: {exc}", motivo_da_recusa(
                    codigo, getattr(exc, "dados", None)))

    async def soltar_tudo(self, t_ms: float) -> None:
        """O zero em tudo que ficou escrito: a extensão que sai não deixa o controle vibrando.

        O zero que a porta recusou antes se tenta uma vez mais: é a última escrita da extensão.
        """
        self.recusados.clear()
        pedidos, self.pedidos_do_corpo = self.pedidos_do_corpo, None
        try:
            await self.aplicar(t_ms, {})
            await self.ligar_o_corpo(t_ms, {})
        finally:
            self.pedidos_do_corpo = pedidos
