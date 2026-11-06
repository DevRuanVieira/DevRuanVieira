#!/usr/bin/env python3
"""Gera o card SVG do README do perfil.

Uso:
    GH_TOKEN=... python scripts/generate.py           # dados reais do GitHub
    python scripts/generate.py --demo                  # dados fictícios, só pra prévia

Soma as contribuições da conta do perfil (GH_LOGIN) e da conta do trabalho. O token precisa
enxergar os repositórios privados do trabalho (token classic com escopo repo).

Só usa a biblioteca padrão do Python (roda no GitHub Actions sem pip install).
Para editar textos e stack, mexa no bloco PERFIL logo abaixo.
"""
from __future__ import annotations

import base64
import json
import os
import random
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

# ─────────────────────────────── PERFIL ────────────────────────────────
PERFIL = {
    "login": os.environ.get("GH_LOGIN", "DevRuanVieira"),
    "login_trabalho": "ruanmVieira",
    "nome": "Ruan Melo Vieira",
    "titulo": "Desenvolvedor Full Stack",
    "sub": "Atena Solutions · projetos internacionais · São Paulo",
    # True = uso no dia a dia; False = também trabalho com
    "stack": [
        ("linguagens", [("TypeScript", True), ("JavaScript", True), ("Java", True),
                        ("C#", True), ("Python", False), ("SQL", True)]),
        ("back-end", [("NestJS", True), ("Node.js", True), ("APIs REST", True),
                      ("Spring Boot", True), (".NET", True)]),
        ("front-end", [("React", True), ("Next.js", True), ("React Native", True),
                       ("Vite", False), ("React Query", False)]),
        ("dados", [("PostgreSQL", True), ("MySQL", True), ("Oracle", True)]),
        ("infra", [("Docker", True), ("Git", True), ("GitHub Actions", False),
                   ("Linux", False), ("CI/CD", False)]),
    ],
    "agora": [
        ("trabalho · atena solutions", "Box Champs",
         "Plataforma de jogos web e mobile: API REST, app React e React Native, tudo em TypeScript."),
        ("trabalho · atena solutions", "The Venue Report",
         "Plataforma com curadoria de espaços para eventos e viagens em grupo."),
        ("projeto pessoal · em desenvolvimento", "Quantis",
         "Plataforma própria de trading com IA para Bitcoin e Ethereum, com um LLM que interpreta notícias. "
         "Roda em modo sombra."),
        ("formação", "FIAP",
         "Bacharelado em Engenharia de Software, conclusão prevista em 2027."),
    ],
}

# ─────────────────────────────── CORES ─────────────────────────────────
TEMA = {
    "bg": "#0E0F12", "line": "#24272E", "text": "#ECEDEF", "muted": "#9AA0AA",
    "dim": "#868C97", "accent": "#5CC8F0", "chip": "#0F2731",
    "heat": ["#1B1E24", "#0F3B4D", "#16698A", "#2EA2CC", "#7AD7F7"],
}

W = 840          # largura dos cards (cabe na coluna do README)
PAD = 36
AQUI = Path(__file__).resolve().parent
FONTES = AQUI / "fonts"
SAIDA = AQUI.parent / "assets"
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

SG4, SG5, MONO = "space-grotesk-latin-400-normal", "space-grotesk-latin-500-normal", "jetbrains-mono-latin-400-normal"
METRICAS = json.loads((FONTES / "metrics.json").read_text(encoding="utf-8"))


def largura(texto: str, fonte: str, tamanho: float) -> float:
    m = METRICAS[fonte]
    media = 600
    return sum(m["w"].get(c, media) for c in texto) * tamanho / m["upm"]


def quebrar(texto: str, fonte: str, tamanho: float, maximo: float) -> list[str]:
    linhas, atual = [], ""
    for palavra in texto.split():
        teste = f"{atual} {palavra}".strip()
        if atual and largura(teste, fonte, tamanho) > maximo:
            linhas.append(atual)
            atual = palavra
        else:
            atual = teste
    if atual:
        linhas.append(atual)
    return linhas


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


# ─────────────────────────────── DADOS ─────────────────────────────────
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      restrictedContributionsCount
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}"""


def api_github(token: str, caminho: str, corpo: bytes | None = None) -> dict:
    req = urllib.request.Request("https://api.github.com" + caminho, data=corpo, headers={
        "Authorization": f"bearer {token}", "Content-Type": "application/json",
        "User-Agent": "profile-card-generator"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def contar(token: str, tipo: str, busca: str) -> int:
    q = urllib.parse.urlencode({"q": busca, "per_page": 1})
    return api_github(token, f"/search/{tipo}?{q}")["total_count"]


def com_niveis(por_dia: dict[date, int]) -> list[tuple[date, int, int]]:
    """Níveis do heatmap em quartis dos dias com contribuição, como o GitHub faz em cada
    conta. Precisa recalcular porque os níveis de duas contas não podem ser somados."""
    positivos = sorted(n for n in por_dia.values() if n)
    cortes = [positivos[len(positivos) * q // 4] for q in (1, 2, 3)] if positivos else []
    return [(dia, n, 1 + sum(n > c for c in cortes) if n else 0) for dia, n in sorted(por_dia.items())]


def buscar_github(token: str) -> dict:
    agora = datetime.now(timezone.utc)
    desde = (agora - timedelta(days=364)).strftime("%Y-%m-%d")
    por_dia: dict[date, int] = {}
    commits = prs = reviews = privados = 0
    for login in (PERFIL["login"], PERFIL["login_trabalho"]):
        corpo = json.dumps({"query": QUERY, "variables": {
            "login": login,
            "from": f"{desde}T00:00:00Z",
            "to": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }}).encode()
        resp = api_github(token, "/graphql", corpo)
        if resp.get("errors"):
            raise SystemExit(f"Erro da API do GitHub: {resp['errors']}")
        cc = resp["data"]["user"]["contributionsCollection"]
        for semana in cc["contributionCalendar"]["weeks"]:
            for d in semana["contributionDays"]:
                dia = date.fromisoformat(d["date"])
                por_dia[dia] = por_dia.get(dia, 0) + d["contributionCount"]
        # O calendário não separa o que é privado em commits, PRs e reviews, então eles vêm da busca.
        c = contar(token, "commits", f"author:{login} committer-date:>={desde}")
        p = contar(token, "issues", f"author:{login} is:pr created:>={desde}")
        r = contar(token, "issues", f"reviewed-by:{login} -author:{login} is:pr created:>={desde}")
        # Token sem acesso aos repositórios privados: para aqui para não gravar cards zerados.
        if cc["restrictedContributionsCount"] and not (c or p or r):
            raise SystemExit(f"O token não enxerga os repositórios privados de {login}. "
                             "Use um token classic com escopo repo. O card não foi alterado.")
        commits += c
        prs += p
        reviews += r
        privados += contar(token, "commits", f"author:{login} is:private committer-date:>={desde}")
    return {
        "dias": com_niveis(por_dia),
        "total": sum(por_dia.values()),
        "commits": commits,
        "prs": prs,
        "reviews": reviews,
        "privados": privados,
        "demo": False,
    }


def dados_demo() -> dict:
    rnd = random.Random(7)
    hoje = date.today()
    inicio = hoje - timedelta(days=364)
    inicio -= timedelta(days=(inicio.weekday() + 1) % 7)  # semana começa no domingo
    dias, d = [], inicio
    while d <= hoje:
        fds = d.weekday() >= 5
        n = 0 if rnd.random() < (0.75 if fds else 0.18) else rnd.choice([1, 2, 3, 4, 5, 6, 8, 11, 14])
        dias.append([d, n, 0])
        d += timedelta(days=1)
    for x in dias:
        x[2] = 0 if x[1] == 0 else 1 if x[1] <= 2 else 2 if x[1] <= 5 else 3 if x[1] <= 9 else 4
    total = sum(x[1] for x in dias)
    return {"dias": [tuple(x) for x in dias], "total": total, "commits": int(total * .78),
            "prs": 96, "reviews": 141, "privados": int(total * .78 * .9), "demo": True}


def sequencias(dias) -> tuple[int, int]:
    maior = atual = 0
    for _, n, _ in dias:
        atual = atual + 1 if n > 0 else 0
        maior = max(maior, atual)
    # sequência atual: hoje ainda pode estar zerado sem quebrar
    atual, seq = 0, list(dias)
    if seq and seq[-1][1] == 0:
        seq = seq[:-1]
    for _, n, _ in reversed(seq):
        if n == 0:
            break
        atual += 1
    return atual, maior


# ─────────────────────────────── SVG ───────────────────────────────────
def fontes_css() -> str:
    regras = []
    for fam, arq, peso in [("SG", SG4, 400), ("SG", SG5, 500), ("Mono", MONO, 400)]:
        b64 = base64.b64encode((FONTES / f"{arq}.woff2").read_bytes()).decode()
        regras.append(f"@font-face{{font-family:'{fam}';font-weight:{peso};"
                      f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return "".join(regras)


def svg(h: int, t: dict, corpo: str, titulo: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" '
            f'role="img" aria-label="{escape(titulo)}">'
            f"<title>{escape(titulo)}</title>"
            f"<style>{fontes_css()}"
            f".sg{{font-family:'SG',system-ui,sans-serif}}.m{{font-family:'Mono',ui-monospace,monospace}}"
            f"text{{text-rendering:geometricPrecision}}"
            f".a{{animation:sobe .6s ease-out both;animation-delay:var(--d)}}"
            f".c{{animation:acende .5s ease-out both;animation-delay:var(--d);"
            f"transform-box:fill-box;transform-origin:center}}"
            f"@keyframes sobe{{from{{opacity:0;transform:translateY(8px)}}}}"
            f"@keyframes acende{{from{{fill:{t['heat'][0]};transform:scale(.55)}}60%{{transform:scale(1.18)}}}}"
            f"@media (prefers-reduced-motion:reduce){{.a,.c{{animation:none}}}}</style>"
            f'<rect x="0.5" y="0.5" width="{W-1}" height="{h-1}" rx="14" fill="{t["bg"]}" stroke="{t["line"]}"/>'
            f"{corpo}</svg>")


def txt(x, y, s, cls, size, fill, weight=400, anchor="start", extra=""):
    return (f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}"{extra}>{escape(s)}</text>')


def anim(d: float) -> str:
    """Atraso da animação de entrada, em segundos."""
    return f' style="--d:{d:.2f}s"'


def entra(d: float) -> str:
    """Abre um grupo que entra na tela com `d` segundos de atraso."""
    return f'<g class="a"{anim(d)}>'


def card_header(d: dict, t: dict, atualizado: str) -> tuple[str, float]:
    p = PERFIL
    o = []
    o.append(txt(PAD, 54, f"~/{p['login']}", "m a", 13, t["accent"], extra=anim(0)))
    o.append(txt(W - PAD, 54, f"atualizado em {atualizado}", "m a", 12, t["dim"], anchor="end", extra=anim(0)))
    o.append(txt(PAD - 2, 104, p["nome"], "sg a", 40, t["text"], 500, extra=' letter-spacing="-0.8"' + anim(.1)))
    o.append(txt(PAD, 136, p["titulo"], "sg a", 19, t["text"], 500, extra=anim(.2)))
    o.append(txt(PAD, 162, p["sub"], "sg a", 14, t["muted"], extra=anim(.3)))

    # heatmap: 53 semanas x 7 dias
    gap = 3
    hx, hy = PAD, 214
    dias = d["dias"]
    primeiro = dias[0][0]
    offset = (primeiro.weekday() + 1) % 7  # domingo = 0
    semanas = (offset + len(dias) + 6) // 7
    passo = (W - 2 * PAD + gap) / semanas   # ocupa a largura toda do card
    cel = round(passo - gap, 2)
    inicio_col = {}
    for i, (dia, n, nivel) in enumerate(dias):
        col, lin = divmod(i + offset, 7)
        x, y = hx + col * passo, hy + lin * passo
        acende = f' class="c"{anim(.45 + col * .018)}' if nivel else ""  # acende da esquerda para a direita
        o.append(f'<rect{acende} x="{x:.2f}" y="{y:.2f}" width="{cel}" height="{cel}" rx="2.5" fill="{t["heat"][nivel]}"/>')
        inicio_col.setdefault(col, dia)
    # rótulo do mês na coluna onde ele começa (pulando se ficar colado no anterior)
    ultimo = -9
    for col in range(semanas):
        dia = inicio_col[col]
        comeca = dia.day <= 7
        if comeca and col - ultimo >= 3 and col <= semanas - 2:
            o.append(txt(hx + col * passo, hy - 10, MESES[dia.month - 1], "m a", 11, t["dim"], extra=anim(.4 + col * .013)))
            ultimo = col
    fim_heat = hy + 7 * passo - gap

    # legenda
    ly = fim_heat + 24
    o.append(entra(1.5))
    o.append(txt(W - PAD, ly, "mais", "m", 11, t["dim"], anchor="end"))
    lx = W - PAD - largura("mais", MONO, 11) - 8
    for i in range(4, -1, -1):
        lx -= 11
        o.append(f'<rect x="{lx:.1f}" y="{ly - 10}" width="11" height="11" rx="2.5" fill="{t["heat"][i]}"/>')
        lx -= 3
    o.append(txt(lx - 5, ly, "menos", "m", 11, t["dim"], anchor="end"))
    pct = round(100 * d["privados"] / d["commits"]) if d["commits"] else 0
    o.append(txt(hx, ly, f"{pct}% dos commits em repositórios privados", "m", 11, t["dim"]))
    o.append("</g>")

    # números
    atual, maior = sequencias(dias)
    stats = [(fmt(d["total"]), "contribuições"), (fmt(d["commits"]), "commits"),
             (fmt(d["prs"]), "pull requests"), (fmt(d["reviews"]), "code reviews"),
             (f"{maior} dias", "maior sequência")]
    sy = ly + 30
    o.append(f'<line x1="{PAD}" y1="{sy}" x2="{W - PAD}" y2="{sy}" stroke="{t["line"]}"/>')
    colw = (W - 2 * PAD) / len(stats)
    for i, (v, rot) in enumerate(stats):
        x = PAD + i * colw
        o.append(entra(1.6 + i * .13))
        if i:
            o.append(f'<line x1="{x - 0.5:.1f}" y1="{sy + 18}" x2="{x - 0.5:.1f}" y2="{sy + 74}" stroke="{t["line"]}"/>')
        cx = x + (0 if i == 0 else 20)
        o.append(txt(cx, sy + 50, v, "sg", 28, t["text"], 500, extra=' letter-spacing="-0.5"'))
        o.append(txt(cx, sy + 72, rot, "m", 11.5, t["muted"]))
        o.append("</g>")
    h = sy + 132
    o.append(txt(PAD, h - 28, "últimos 12 meses · inclui repositórios privados do trabalho", "m a", 11, t["dim"], extra=anim(2.3)))
    if d["demo"]:
        o.append(txt(W - PAD, h - 28, "DADOS DE EXEMPLO", "m", 11, "#E5484D", anchor="end"))
    return "".join(o), h


def chip(x, y, rotulo, forte, t) -> tuple[str, float]:
    tam = 13.5
    w = largura(rotulo, SG5, tam) + 26
    if forte:
        r = (f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="30" rx="15" fill="{t["chip"]}" stroke="{t["accent"]}"/>'
             + txt(x + w / 2, y + 20, rotulo, "sg", tam, t["text"], 500, "middle"))
    else:
        r = (f'<rect x="{x + .5:.1f}" y="{y + .5}" width="{w - 1:.1f}" height="29" rx="14.5" fill="none" stroke="{t["line"]}"/>'
             + txt(x + w / 2, y + 20, rotulo, "sg", tam, t["muted"], 400, "middle"))
    return r, w


def card_stack(t: dict, base: float) -> tuple[str, float]:
    o = [txt(PAD, 52, "// stack", "m a", 13, t["accent"], extra=anim(base)), entra(base + .05)]
    # legenda à direita
    lx = W - PAD
    for rot, forte in [("também trabalho com", False), ("no dia a dia", True)]:
        wt = largura(rot, MONO, 11.5)
        o.append(txt(lx, 52, rot, "m", 11.5, t["muted"], anchor="end"))
        lx -= wt + 8
        if forte:
            o.append(f'<rect x="{lx - 18}" y="42" width="18" height="12" rx="6" fill="{t["chip"]}" stroke="{t["accent"]}"/>')
        else:
            o.append(f'<rect x="{lx - 17.5}" y="42.5" width="17" height="11" rx="5.5" fill="none" stroke="{t["line"]}"/>')
        lx -= 18 + 22
    o.append("</g>")
    y = 80
    col_rot = PAD + 118
    # entram as linhas, depois os chips marcados e por último os demais
    fortes = sum(forte for _, itens in PERFIL["stack"] for _, forte in itens)
    n_forte = n_outro = 0
    for i, (grupo, itens) in enumerate(PERFIL["stack"]):
        o.append(entra(base + .1 + i * .07))
        if i:
            o.append(f'<line x1="{PAD}" y1="{y - 9}" x2="{W - PAD}" y2="{y - 9}" stroke="{t["line"]}"/>')
        o.append(txt(PAD, y + 20, grupo, "m", 12, t["dim"]))
        o.append("</g>")
        x = col_rot
        for rot, forte in itens:
            _, w = chip(0, 0, rot, forte, t)
            if x + w > W - PAD:
                x = col_rot
                y += 38
            s, w = chip(x, y, rot, forte, t)
            if forte:
                atraso = base + .45 + n_forte * .05
                n_forte += 1
            else:
                atraso = base + .55 + fortes * .05 + n_outro * .04
                n_outro += 1
            o.append(f"{entra(atraso)}{s}</g>")
            x += w + 8
        y += 30 + 18
    h = y + 18
    return "".join(o), h


def card_agora(t: dict, base: float) -> tuple[str, float]:
    o = [txt(PAD, 52, "// agora", "m a", 13, t["accent"], extra=anim(base))]
    cols, gx = 2, 36
    cw = (W - 2 * PAD - gx) / cols
    y0 = 84
    alturas = []
    blocos = []
    for i, (rot, tit, desc) in enumerate(PERFIL["agora"]):
        linhas = quebrar(desc, SG4, 14, cw)
        blocos.append((rot, tit, linhas))
        alturas.append(52 + 21 * len(linhas))
    linhas_grid = (len(blocos) + cols - 1) // cols
    y = y0
    for r in range(linhas_grid):
        hr = max(alturas[r * cols:(r + 1) * cols])
        if r:
            o.append(f'<line x1="{PAD}" y1="{y - 18}" x2="{W - PAD}" y2="{y - 18}" stroke="{t["line"]}"/>')
        for c in range(cols):
            k = r * cols + c
            if k >= len(blocos):
                continue
            rot, tit, linhas = blocos[k]
            x = PAD + c * (cw + gx)
            o.append(entra(base + .15 + k * .25))  # um bloco de cada vez
            o.append(txt(x, y, rot, "m", 11.5, t["dim"]))
            o.append(txt(x, y + 28, tit, "sg", 19, t["text"], 500))
            for j, ln in enumerate(linhas):
                o.append(txt(x, y + 54 + j * 21, ln, "sg", 14, t["muted"]))
            o.append("</g>")
        y += hr + 36
    h = y - 8
    return "".join(o), h


def card_perfil(d: dict, t: dict, atualizado: str) -> str:
    """Tudo num card só: cabeçalho + contribuições, stack e o que está fazendo agora."""
    partes = []
    corpo, hh = card_header(d, t, atualizado)
    partes.append(corpo)
    y = hh - 8
    # cada seção começa um pouco depois da anterior, e tudo termina em cerca de 3 segundos
    for secao, base in ((card_stack, .6), (card_agora, 1.4)):
        corpo, hs = secao(t, base)
        partes.append(f'<line x1="{PAD}" y1="{y}" x2="{W - PAD}" y2="{y}" stroke="{t["line"]}"/>')
        ty = y - 10
        partes.append(f'<g transform="translate(0,{ty})">{corpo}</g>')
        y = ty + hs
    h = int(y + 14)
    p = PERFIL
    titulo = (f"{p['nome']} — {p['titulo']}. {fmt(d['total'])} contribuições no último ano. Stack: "
              + ", ".join(r for _, it in p["stack"] for r, _ in it))
    return svg(h, t, "".join(partes), titulo)


def main() -> None:
    demo = "--demo" in sys.argv
    if demo:
        d = dados_demo()
    else:
        token = os.environ.get("GH_TOKEN")
        if not token:
            raise SystemExit("Defina GH_TOKEN (ou rode com --demo).")
        d = buscar_github(token)
    try:
        from zoneinfo import ZoneInfo
        agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    except Exception:
        agora = datetime.now(timezone(timedelta(hours=-3)))
    atualizado = agora.strftime("%d/%m/%Y")
    SAIDA.mkdir(exist_ok=True)
    (SAIDA / "perfil.svg").write_text(card_perfil(d, TEMA, atualizado), encoding="utf-8")
    print(f"ok: {fmt(d['total'])} contribuições, {fmt(d['commits'])} commits"
          + (" (DEMO)" if demo else ""))


if __name__ == "__main__":
    main()
