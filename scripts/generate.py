#!/usr/bin/env python3
"""Gera os cards SVG do README do perfil.

Uso:
    GH_TOKEN=... python scripts/generate.py           # dados reais do GitHub
    python scripts/generate.py --demo                  # dados fictícios, só pra prévia

Soma as contribuições da conta do perfil (GH_LOGIN) e da conta do trabalho. GH_TOKEN pode
ser qualquer token, como o github.token do Actions: a API só entrega o que já aparece no
perfil público das contas, incluindo a contagem de contribuições privadas.

Só usa a biblioteca padrão do Python (roda no GitHub Actions sem pip install).
Para editar textos e stack, mexa no bloco PERFIL logo abaixo.
"""
from __future__ import annotations

import base64
import json
import os
import random
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

# ─────────────────────────────── PERFIL ────────────────────────────────
PERFIL = {
    "login": os.environ.get("GH_LOGIN", "DevRuanVieira"),
    "login_trabalho": "ruanmVieira",
    "inicio": date(2025, 7, 1),  # primeiro dia mostrado no heatmap e nos números
    "periodo": "desde julho de 2025",
    "nome": "Ruan Melo Vieira",
    "titulo": "Desenvolvedor Full Stack",
    "sub": "Atena Solutions · projetos internacionais, comunicação em inglês · São Paulo",
    # True = uso no dia a dia; False = também trabalho com
    "stack": [
        ("linguagens", [("TypeScript", True), ("JavaScript", True), ("Java", False),
                        ("C#", False), ("Python", False), ("SQL", False)]),
        ("back-end", [("NestJS", True), ("Node.js", True), ("APIs REST", True),
                      ("Spring Boot", False), (".NET", False)]),
        ("front-end", [("React", True), ("Next.js", True), ("React Native", True),
                       ("Vite", False), ("React Query", False)]),
        ("dados", [("PostgreSQL", False), ("MySQL", False), ("Oracle", False)]),
        ("infra", [("Docker", False), ("Git", True), ("GitHub Actions", False),
                   ("Linux", False), ("CI/CD", False)]),
    ],
    "agora": [
        ("trabalho · atena solutions", "Box Champs",
         "Plataforma de jogos web e mobile: API REST, app React e React Native, tudo em TypeScript."),
        ("trabalho · atena solutions", "Venue Report",
         "APIs e regras de negócio em NestJS num sistema em produção, modernizando um back-end legado."),
        ("projeto pessoal · em andamento", "Pluton",
         "Modelo preditivo de preço do Bitcoin em Python."),
        ("formação", "FIAP",
         "Bacharelado em Engenharia de Software, conclusão prevista em 2027."),
    ],
}

# ─────────────────────────────── TEMAS ─────────────────────────────────
TEMAS = {
    "dark": {
        "bg": "#0E0F12", "line": "#24272E", "text": "#ECEDEF", "muted": "#9AA0AA",
        "dim": "#868C97", "accent": "#F5A524", "chip": "#2A2011",
        "heat": ["#1B1E24", "#4A3410", "#86570F", "#C47E17", "#F5A524"],
    },
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
# Sem acesso aos repositórios privados, a API só informa quantas contribuições houve por
# dia: tudo vem como "restricted", sem separar commits, PRs e reviews.
QUERY = """
query($pessoal: String!, $trabalho: String!, $from: DateTime!, $to: DateTime!) {
  pessoal: user(login: $pessoal) { ...contribuicoes }
  trabalho: user(login: $trabalho) { ...contribuicoes }
}
fragment contribuicoes on User {
  contributionsCollection(from: $from, to: $to) {
    restrictedContributionsCount
    contributionCalendar {
      weeks { contributionDays { date contributionCount } }
    }
  }
}"""


def com_niveis(por_dia: dict[date, int]) -> list[tuple[date, int, int]]:
    """Níveis do heatmap em quartis dos dias com contribuição, como o GitHub faz em cada
    conta. Precisa recalcular porque os níveis de duas contas não podem ser somados."""
    positivos = sorted(n for n in por_dia.values() if n)
    cortes = [positivos[len(positivos) * q // 4] for q in (1, 2, 3)] if positivos else []
    return [(dia, n, 1 + sum(n > c for c in cortes) if n else 0) for dia, n in sorted(por_dia.items())]


def janelas(inicio: date, fim: date):
    """Divide o período em janelas de até um ano, o limite de cada consulta da API."""
    while inicio <= fim:
        ate = min(inicio + timedelta(days=364), fim)
        yield inicio, ate
        inicio = ate + timedelta(days=1)


def buscar_github(token: str) -> dict:
    contas: dict[str, dict[date, int]] = {"pessoal": {}, "trabalho": {}}
    privados = 0
    for de, ate in janelas(PERFIL["inicio"], datetime.now(timezone.utc).date()):
        corpo = json.dumps({"query": QUERY, "variables": {
            "pessoal": PERFIL["login"],
            "trabalho": PERFIL["login_trabalho"],
            "from": f"{de}T00:00:00Z",
            "to": f"{ate}T23:59:59Z",
        }}).encode()
        req = urllib.request.Request("https://api.github.com/graphql", data=corpo, headers={
            "Authorization": f"bearer {token}", "Content-Type": "application/json",
            "User-Agent": "profile-card-generator"})
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.load(r)
        if resp.get("errors"):
            raise SystemExit(f"Erro da API do GitHub: {resp['errors']}")
        for nome, por_dia in contas.items():
            cc = resp["data"][nome]["contributionsCollection"]
            privados += cc["restrictedContributionsCount"]
            for semana in cc["contributionCalendar"]["weeks"]:
                for d in semana["contributionDays"]:
                    por_dia[date.fromisoformat(d["date"])] = d["contributionCount"]
    pessoal, trabalho = contas["pessoal"], contas["trabalho"]
    soma = {dia: pessoal.get(dia, 0) + trabalho.get(dia, 0) for dia in pessoal.keys() | trabalho.keys()}
    return {
        "dias": com_niveis(soma),
        "total": sum(soma.values()),
        "trabalho": sum(trabalho.values()),
        "pessoal": sum(pessoal.values()),
        "privados": privados,
        "demo": False,
    }


def dados_demo() -> dict:
    rnd = random.Random(7)
    hoje = date.today()
    dias, d = [], PERFIL["inicio"]
    while d <= hoje:
        fds = d.weekday() >= 5
        n = 0 if rnd.random() < (0.75 if fds else 0.18) else rnd.choice([1, 2, 3, 4, 5, 6, 8, 11, 14])
        dias.append([d, n, 0])
        d += timedelta(days=1)
    for x in dias:
        x[2] = 0 if x[1] == 0 else 1 if x[1] <= 2 else 2 if x[1] <= 5 else 3 if x[1] <= 9 else 4
    total = sum(x[1] for x in dias)
    trabalho = int(total * .9)
    return {"dias": [tuple(x) for x in dias], "total": total, "trabalho": trabalho,
            "pessoal": total - trabalho, "privados": trabalho, "demo": True}


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
            f"text{{text-rendering:geometricPrecision}}</style>"
            f'<rect x="0.5" y="0.5" width="{W-1}" height="{h-1}" rx="14" fill="{t["bg"]}" stroke="{t["line"]}"/>'
            f"{corpo}</svg>")


def txt(x, y, s, cls, size, fill, weight=400, anchor="start", extra=""):
    return (f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}"{extra}>{escape(s)}</text>')


def card_header(d: dict, t: dict, atualizado: str) -> str:
    p = PERFIL
    o = []
    o.append(txt(PAD, 54, f"~/{p['login']}", "m", 13, t["accent"]))
    o.append(txt(W - PAD, 54, f"atualizado em {atualizado}", "m", 12, t["dim"], anchor="end"))
    o.append(txt(PAD - 2, 104, p["nome"], "sg", 40, t["text"], 500, extra=' letter-spacing="-0.8"'))
    o.append(txt(PAD, 136, p["titulo"], "sg", 19, t["text"], 500))
    o.append(txt(PAD, 162, p["sub"], "sg", 14, t["muted"]))

    # heatmap: uma coluna por semana, 7 dias em cada
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
        o.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{cel}" height="{cel}" rx="2.5" fill="{t["heat"][nivel]}"/>')
        inicio_col.setdefault(col, dia)
    # rótulo do mês na coluna onde ele começa (pulando se ficar colado no anterior)
    ultimo = -9
    for col in range(semanas):
        dia = inicio_col[col]
        comeca = dia.day <= 7
        if comeca and col - ultimo >= 3 and col <= semanas - 2:
            # com mais de 12 meses, janeiro mostra o ano para os meses repetidos não confundirem
            rotulo = str(dia.year) if dia.month == 1 else MESES[dia.month - 1]
            o.append(txt(hx + col * passo, hy - 10, rotulo, "m", 11, t["dim"]))
            ultimo = col
    fim_heat = hy + 7 * passo - gap

    # legenda
    ly = fim_heat + 24
    o.append(txt(W - PAD, ly, "mais", "m", 11, t["dim"], anchor="end"))
    lx = W - PAD - largura("mais", MONO, 11) - 8
    for i in range(4, -1, -1):
        lx -= 11
        o.append(f'<rect x="{lx:.1f}" y="{ly - 10}" width="11" height="11" rx="2.5" fill="{t["heat"][i]}"/>')
        lx -= 3
    o.append(txt(lx - 5, ly, "menos", "m", 11, t["dim"], anchor="end"))
    pct = round(100 * d["privados"] / d["total"]) if d["total"] else 0
    o.append(txt(hx, ly, f"{pct}% das contribuições em repositórios privados", "m", 11, t["dim"]))

    # números
    atual, maior = sequencias(dias)
    ativos = sum(1 for _, n, _ in dias if n)
    stats = [(fmt(d["total"]), "contribuições"), (fmt(d["trabalho"]), "no trabalho"),
             (fmt(d["pessoal"]), "pessoais"), (fmt(ativos), "dias ativos"),
             (f"{maior} dias", "maior sequência")]
    sy = ly + 30
    o.append(f'<line x1="{PAD}" y1="{sy}" x2="{W - PAD}" y2="{sy}" stroke="{t["line"]}"/>')
    colw = (W - 2 * PAD) / len(stats)
    for i, (v, rot) in enumerate(stats):
        x = PAD + i * colw
        if i:
            o.append(f'<line x1="{x - 0.5:.1f}" y1="{sy + 18}" x2="{x - 0.5:.1f}" y2="{sy + 74}" stroke="{t["line"]}"/>')
        cx = x + (0 if i == 0 else 20)
        o.append(txt(cx, sy + 50, v, "sg", 28, t["text"], 500, extra=' letter-spacing="-0.5"'))
        o.append(txt(cx, sy + 72, rot, "m", 11.5, t["muted"]))
    h = sy + 132
    o.append(txt(PAD, h - 28, f"{p['periodo']} · inclui repositórios privados do trabalho", "m", 11, t["dim"]))
    if d["demo"]:
        o.append(txt(W - PAD, h - 28, "DADOS DE EXEMPLO", "m", 11, "#E5484D", anchor="end"))
    return svg(h, t, "".join(o), f"{p['nome']} — {p['titulo']}. {fmt(d['total'])} contribuições {p['periodo']}.")


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


def card_stack(t: dict) -> str:
    o = [txt(PAD, 52, "// stack", "m", 13, t["accent"])]
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
    y = 80
    col_rot = PAD + 118
    for i, (grupo, itens) in enumerate(PERFIL["stack"]):
        if i:
            o.append(f'<line x1="{PAD}" y1="{y - 9}" x2="{W - PAD}" y2="{y - 9}" stroke="{t["line"]}"/>')
        o.append(txt(PAD, y + 20, grupo, "m", 12, t["dim"]))
        x = col_rot
        for rot, forte in itens:
            _, w = chip(0, 0, rot, forte, t)
            if x + w > W - PAD:
                x = col_rot
                y += 38
            s, w = chip(x, y, rot, forte, t)
            o.append(s)
            x += w + 8
        y += 30 + 18
    h = y + 18
    return svg(h, t, "".join(o), "Stack: " + ", ".join(r for _, it in PERFIL["stack"] for r, _ in it))


def card_agora(t: dict) -> str:
    o = [txt(PAD, 52, "// agora", "m", 13, t["accent"])]
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
            o.append(txt(x, y, rot, "m", 11.5, t["dim"]))
            o.append(txt(x, y + 28, tit, "sg", 19, t["text"], 500))
            for j, ln in enumerate(linhas):
                o.append(txt(x, y + 54 + j * 21, ln, "sg", 14, t["muted"]))
        y += hr + 36
    h = y - 8
    return svg(h, t, "".join(o), "Agora: " + "; ".join(f"{b[1]}" for b in PERFIL["agora"]))


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
    for nome, t in TEMAS.items():
        (SAIDA / f"header-{nome}.svg").write_text(card_header(d, t, atualizado), encoding="utf-8")
        (SAIDA / f"stack-{nome}.svg").write_text(card_stack(t), encoding="utf-8")
        (SAIDA / f"agora-{nome}.svg").write_text(card_agora(t), encoding="utf-8")
    print(f"ok: {fmt(d['total'])} contribuições, {fmt(d['trabalho'])} no trabalho, {fmt(d['pessoal'])} pessoais"
          + (" (DEMO)" if demo else ""))


if __name__ == "__main__":
    main()
