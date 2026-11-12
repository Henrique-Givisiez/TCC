#!/usr/bin/env python3
"""Caracterização visual da A1; somente leitura dos registros primários."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "experiment_results/legitimate-characterization-a1-20261106T202205Z"
OUT = ROOT / "reports/a1_visual_characterization_20261112"
ORDER = ["L2", "L6", "L3", "L7"]
LABEL = {"L2": "L2 — 2 fontes, 16 RPS", "L6": "L6 — 4 fontes, 16 RPS", "L3": "L3 — 2 fontes, 32 RPS", "L7": "L7 — 4 fontes, 32 RPS"}
COLOR = {"L2": "#17698c", "L6": "#bc6527", "L3": "#493f94", "L7": "#a12c55"}
STYLE = {"L2": "-", "L6": "--", "L3": "-.", "L7": ":"}
FAMILY = {"A": "A_geracao", "B": "B_recursos", "C": "C_workers", "D": "D_http", "E": "E_integradas"}
plt.rcParams.update({"font.size": 10, "axes.titlesize": 12, "axes.labelsize": 10, "figure.titlesize": 14, "pdf.fonttype": 42, "savefig.facecolor": "white"})

def read_jsonl(path):
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]

def hash_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def load_run(k):
    p = SRC / k
    paths = [p / "raw" / x for x in ("effective_config.json", "run_status.json", "request_log.csv", "rtt_log.csv", "victim_stats.jsonl", "diagnostics/victim/events.jsonl")]
    paths += sorted((p / "raw/source_artifacts").glob("normal_*/output/diagnostics/events.jsonl"))
    hashes = {str(x.relative_to(ROOT)): hash_file(x) for x in paths}
    cfg = json.loads(paths[0].read_text()); status = json.loads(paths[1].read_text())
    assert status["status"] == "completed" and status["end_reason"] == "simulation_end" and status["errors"] == []
    assert cfg["duration_seconds"] == 150 and cfg["attack"]["enabled"] is False
    assert cfg["topology"]["mode"] == "direct" and cfg["server"]["process_pool_workers"] == 2
    assert cfg["normal_traffic"]["max_concurrent_sends"] == 64 and cfg["normal_traffic"]["endpoint"] == "/medium"
    assert (cfg["normal_traffic"]["clients"], cfg["normal_traffic"]["rate"]) == {"L2": (2,8), "L6": (4,4), "L3": (2,16), "L7": (4,8)}[k]
    req = pd.read_csv(paths[2]).fillna({"error_type": ""})
    assert len(req) == req.request_id.nunique() and set(req.run_id) == {status["run_id"]}
    assert (req.duration_ms >= 0).all() and (req.end_elapsed_seconds >= req.elapsed_seconds).all()
    assert np.allclose(req.end_elapsed_seconds - req.elapsed_seconds, req.duration_ms / 1000, atol=.002)
    rtt = pd.read_csv(paths[3]); assert len(rtt) == len(req) and set(rtt.request_id) == set(req.request_id)
    stats_raw = read_jsonl(paths[4])
    assert {x["metrics"]["name"] for x in stats_raw} == {"target_instance_1"}
    stats = pd.DataFrame([{"t": x["monotonic"]-status["experiment_start_monotonic"], "cpu": x["metrics"]["cpu_percent"], "mem": x["metrics"]["raw_mem_usage"] / 1048576} for x in stats_raw]).sort_values("t")
    ev = read_jsonl(paths[5]); works = pd.DataFrame([{"request_id": x["request_id"], "submit": x["work_submitted_at"]-status["experiment_start_monotonic"], "start": x["work_started_at"]-status["experiment_start_monotonic"], "finish": x["work_finished_at"]-status["experiment_start_monotonic"]} for x in ev if x["kind"] == "handler_finished" and x.get("phase") != "capture_audit"])
    assert len(works) == works.request_id.nunique() and set(works.request_id) == set(req.request_id)
    assert ((works["start"] >= works["submit"]) & (works["finish"] >= works["start"])).all()
    clocks = {(x["worker_clock"]["kind"], x["worker_clock"]["time_namespace"]) for x in ev if x["kind"] == "handler_finished" and x.get("phase") != "capture_audit"}
    assert len(clocks) == 1 and next(iter(clocks))[0] == "CLOCK_MONOTONIC"
    src_counts = Counter()
    for path in paths[6:]:
        a = read_jsonl(path); src_counts.update(x["kind"] for x in a)
        ids = {x["request_id"] for x in a if x["kind"] == "http_started"}
        assert len(ids) == sum(x["kind"] == "http_started" for x in a)
    assert src_counts["http_started"] == len(req) == src_counts["http_finished"]
    works["wait_ms"] = (works["start"] - works["submit"]) * 1000
    works = works.merge(req[["request_id", "elapsed_seconds"]], on="request_id", validate="one_to_one")
    return {"cfg": cfg, "status": status, "req": req, "rtt": rtt, "stats": stats, "works": works, "sources": dict(src_counts), "hashes": hashes, "clock": list(clocks)[0]}

def step_counts(w, tmax=150):
    events = []
    for row in w.itertuples():
        events += [(row.submit, 0, 1, 0), (row.start, 1, -1, 1), (row.finish, 2, 0, -1)]
    events.sort(key=lambda z: (z[0], z[1]))
    waiting = running = 0; xs = [0.]; ws = [0]; rs = [0]
    for t, _, dw, dr in events:
        waiting += dw; running += dr
        assert 0 <= waiting and 0 <= running <= 2
        xs.append(t); ws.append(waiting); rs.append(running)
    if xs[-1] < tmax:
        xs.append(tmax); ws.append(waiting); rs.append(running)
    return np.array(xs), np.array(ws), np.array(rs)

def observed_fraction(x, r):
    duration = np.zeros(3)
    for a,b,v in zip(x[:-1],x[1:],r[:-1]):
        d = max(0, min(b,150)-max(a,30))
        if d: duration[int(v)] += d
    assert np.isclose(sum(duration), 120)
    return duration / 120

def bins_http(req):
    r = req[(req.elapsed_seconds >= 0) & (req.elapsed_seconds < 150)]
    starts = np.histogram(r.elapsed_seconds, bins=np.arange(151))[0]
    # 10 s: each window has sufficient observations for descriptive p95.
    good = r[(r.outcome == "response") & (r.http_status.between(200,299))].copy()
    good["bin"] = np.floor(good.elapsed_seconds / 10).astype(int)
    agg = good.groupby("bin").duration_ms.agg(n="count", med="median", p95=lambda v: np.percentile(v,95)).reindex(range(15))
    agg.loc[agg.n < 20, "p95"] = np.nan
    return starts, agg

def shade(ax):
    ax.axvspan(30,150,color="#e5ecf1",alpha=.45,zorder=-10)
    ax.axvline(30,color="#65717a",lw=.8,ls=":")
    ax.set_xlim(0,150); ax.grid(alpha=.2); ax.set_xlabel("Tempo relativo à execução (s)")

figures = []
def save(fig, family, name):
    folder = OUT / "figures" / FAMILY[family]; folder.mkdir(parents=True,exist_ok=True)
    fig.tight_layout(rect=(0,0,1,.96) if fig._suptitle else None)
    for fmt in ("png","pdf"):
        path = folder / f"{name}.{fmt}"; fig.savefig(path,dpi=300,bbox_inches="tight"); figures.append(str(path.relative_to(OUT)))
    plt.close(fig)

def line(ax,k,x,y,label=None,**kw):
    ax.plot(x,y,color=COLOR[k],ls=STYLE[k],lw=1.5,label=label or k,**kw)

def matrix(code, metric, title, ylabel, render, ylim=None):
    fig,axes=plt.subplots(2,2,figsize=(12,7),sharex=True,sharey=ylim is not None)
    for ax,k in zip(axes.ravel(),["L2","L3","L6","L7"]):
        render(ax,k);shade(ax);ax.set_title(LABEL[k]);ax.set_ylabel(ylabel)
        if ylim is not None:ax.set_ylim(*ylim)
    fig.suptitle(title);save(fig,code,f"{metric}_matriz")

def ecdf(ax, vals, k):
    x=np.sort(np.asarray(vals));line(ax,k,x,np.arange(1,len(x)+1)/len(x),label=f"{k} (n={len(x)})")

def main():
    runs={k:load_run(k) for k in ORDER}
    for k,d in runs.items():
        x,w,r=step_counts(d["works"]);d["steps"]=(x,w,r);d["fractions"]=observed_fraction(x,r)
        d["rps"],d["http_bins"]=bins_http(d["req"])
        d["main_req"]=d["req"][(d["req"].elapsed_seconds>=30)&(d["req"].elapsed_seconds<150)]
        d["main_stats"]=d["stats"][(d["stats"].t>=30)&(d["stats"].t<150)]
        d["main_works"]=d["works"][(d["works"].elapsed_seconds>=30)&(d["works"].elapsed_seconds<150)]
    # A1
    fig,ax=plt.subplots(figsize=(10,5));xx=np.arange(4);nom=[runs[k]["cfg"]["normal_traffic"]["rate"]*runs[k]["cfg"]["normal_traffic"]["clients"] for k in ORDER]
    eff=[len(runs[k]["main_req"])/120 for k in ORDER]
    ax.bar(xx-.19,nom,.38,label="Nominal",color="#aab8c2");ax.bar(xx+.19,eff,.38,label="HTTP iniciado",color=[COLOR[k] for k in ORDER],hatch="//")
    ax.set_xticks(xx,[LABEL[k] for k in ORDER],rotation=12,ha="right");ax.set_ylabel("Requisições iniciadas por segundo (RPS)");ax.set_ylim(0,37);ax.legend();ax.grid(axis="y",alpha=.2);ax.set_title("A1 — RPS nominal e HTTP iniciado, [30,150) s");save(fig,"A","A1_rps_nominal_efetivo")
    # A2
    for k in ORDER:
        fig,ax=plt.subplots(figsize=(11,4));ax.step(np.arange(150),runs[k]["rps"],where="post",color=COLOR[k]);shade(ax);ax.set_ylabel("Requisições iniciadas por segundo (RPS)");ax.set_title(f"A2 — RPS HTTP iniciado por janela de 1 s: {LABEL[k]}");save(fig,"A",f"A2_rps_temporal_{k}")
    fig,ax=plt.subplots(figsize=(12,5))
    for k in ORDER:line(ax,k,np.arange(150),runs[k]["rps"],LABEL[k])
    shade(ax);ax.set_ylabel("Requisições iniciadas por segundo (RPS)");ax.legend(ncol=2,loc="upper center",bbox_to_anchor=(.5,-.17));ax.set_title("A2 — RPS HTTP iniciado por janela de 1 s: A1");save(fig,"A","A2_rps_temporal_comparativo")
    matrix("E","E2_rps","E2 — RPS HTTP iniciado nas quatro configurações","Requisições/s",lambda ax,k:ax.step(np.arange(150),runs[k]["rps"],where="post",color=COLOR[k]),(0,max(max(d["rps"]) for d in runs.values())*1.1))
    # B1, B3 summary
    for field,code,ylabel,title in [("cpu","B1","CPU da vítima (%)","B1 — CPU Docker da vítima: observações em [30,150) s"),("mem","B3","Memória da vítima (MiB)","B3 — Memória do contêiner da vítima em [30,150) s")]:
        fig,ax=plt.subplots(figsize=(10,5));vals=[runs[k]["main_stats"][field].to_numpy() for k in ORDER]
        bp=ax.boxplot(vals,positions=np.arange(4),patch_artist=True,showfliers=True,medianprops={"color":"black"})
        for patch,k in zip(bp["boxes"],ORDER):patch.set_facecolor(COLOR[k]);patch.set_alpha(.45)
        ax.scatter(range(4),[np.mean(v) for v in vals],marker="D",color="black",s=28,label="Média")
        ax.set_xticks(range(4),[LABEL[k] for k in ORDER],rotation=12,ha="right");ax.set_ylabel(ylabel);ax.legend();ax.grid(axis="y",alpha=.2);ax.set_title(title);save(fig,"B",f"{code}_{field}_comparativo")
    # B2, B4, E2 resources
    for field,code,ylabel in [("cpu","B2","CPU da vítima (%)"),("mem","B4","Memória da vítima (MiB)")]:
        for k in ORDER:
            d=runs[k]["stats"];fig,ax=plt.subplots(figsize=(11,4));line(ax,k,d.t,d[field],marker="o",ms=3);shade(ax);ax.set_ylabel(ylabel);ax.set_title(f"{code} — {ylabel}: {LABEL[k]}");save(fig,"B",f"{code}_{field}_temporal_{k}")
        fig,ax=plt.subplots(figsize=(12,5))
        for k in ORDER:
            d=runs[k]["stats"];line(ax,k,d.t,d[field],LABEL[k],marker="o",ms=2)
        shade(ax);ax.set_ylabel(ylabel);ax.legend(ncol=2,loc="upper center",bbox_to_anchor=(.5,-.18));ax.set_title(f"{code} — {ylabel} nas quatro configurações");save(fig,"B",f"{code}_{field}_temporal_comparativo")
        render=lambda ax,k,field=field:line(ax,k,runs[k]["stats"].t,runs[k]["stats"][field],marker="o",ms=2)
        lim=(0,max(d["stats"][field].max() for d in runs.values())*1.08) if field=="cpu" else (min(d["stats"][field].min() for d in runs.values())-1,max(d["stats"][field].max() for d in runs.values())+1)
        matrix("B",f"{code}_{field}_temporal",f"{code} — {ylabel}: matriz A1",ylabel,render,lim)
        matrix("E",f"E2_{field}",f"E2 — {ylabel}: matriz A1",ylabel,render,lim)
    # C1, C2, E2 worker series
    for idx,code,metric,ylabel in [(2,"C1","ocupacao_workers","Workers ocupados (quantidade)"),(1,"C2","operacoes_aguardando","Operações aguardando (quantidade)")]:
        lim=(0,2.2) if code=="C1" else (0,max(d["steps"][1].max() for d in runs.values())+1)
        for k in ORDER:
            x,w,r=runs[k]["steps"];y=r if code=="C1" else w
            fig,ax=plt.subplots(figsize=(11,4));ax.step(x,y,where="post",color=COLOR[k],lw=1.3);shade(ax);ax.set_ylim(*lim);ax.set_ylabel(ylabel);ax.set_title(f"{code} — {ylabel}: {LABEL[k]}");save(fig,"C",f"{code}_{metric}_{k}")
        render=lambda ax,k,idx=idx:ax.step(runs[k]["steps"][0],runs[k]["steps"][idx],where="post",color=COLOR[k],lw=1)
        matrix("C",f"{code}_{metric}",f"{code} — {ylabel}: matriz A1",ylabel,render,lim)
        matrix("E",f"E2_{metric}",f"E2 — {ylabel}: matriz A1",ylabel,render,lim)
    fig,ax=plt.subplots(figsize=(9,4));bottom=np.zeros(4)
    for i,name,hatch in [(0,"Zero",""),(1,"Um","//"),(2,"Dois","xx")]:
        v=np.array([runs[k]["fractions"][i] for k in ORDER]);ax.bar(range(4),v,bottom=bottom,label=name,hatch=hatch,color="#9bb8c7" if i==0 else "#567f9a" if i==1 else "#244e6e");bottom+=v
    ax.set_xticks(range(4),ORDER);ax.set_ylabel("Fração do tempo em [30,150)");ax.legend(title="Workers ocupados",ncol=3);ax.set_title("C1 — Fração do tempo por ocupação dos workers");save(fig,"C","C1_fracao_ocupacao")
    # C3, D1 distributions
    for code,field,ylabel,selector in [("C3","wait_ms","Espera por worker (ms)",lambda k:runs[k]["main_works"].wait_ms),("D1","duration_ms","Duração HTTP (ms)",lambda k:runs[k]["main_req"].query("outcome == 'response' and 200 <= http_status <= 299").duration_ms)]:
        vals=[selector(k).to_numpy() for k in ORDER]
        fig,ax=plt.subplots(figsize=(10,5));bp=ax.boxplot(vals,patch_artist=True,showfliers=False,whis=(5,95))
        for patch,k in zip(bp["boxes"],ORDER):patch.set_facecolor(COLOR[k]);patch.set_alpha(.55)
        ax.set_xticks(range(1,5),ORDER);ax.set_ylabel(ylabel);ax.grid(axis="y",alpha=.2);ax.set_title(f"{code} — Distribuição de {ylabel.lower()} em [30,150) s (caixas; bigodes p5–p95)");save(fig,"C" if code=="C3" else "D",f"{code}_{field}_boxplot")
        fig,ax=plt.subplots(figsize=(10,5))
        for k,v in zip(ORDER,vals):ecdf(ax,v,k)
        ax.set_ylabel("Fração acumulada");ax.set_xlabel(ylabel);ax.grid(alpha=.2);ax.legend();ax.set_title(f"{code} — ECDF de {ylabel.lower()} em [30,150) s");save(fig,"C" if code=="C3" else "D",f"{code}_{field}_ecdf")
    # C4: number waiting immediately before each work submission; event order tie policy.
    for k in ORDER:
        w=runs[k]["works"].sort_values("submit").copy();x,waiting,_=runs[k]["steps"]
        indices=np.searchsorted(x,w["submit"].to_numpy(),side="left")-1
        w["waiting_before"] = waiting[np.maximum(indices,0)]
        runs[k]["works_with_backlog"]=w
    fig,axes=plt.subplots(2,2,figsize=(11,7),sharex=True,sharey=True)
    for ax,k in zip(axes.ravel(),["L2","L3","L6","L7"]):
        w=runs[k]["works_with_backlog"];w=w[(w.elapsed_seconds>=30)&(w.elapsed_seconds<150)]
        ax.scatter(w.waiting_before,w.wait_ms,s=9,alpha=.25,color=COLOR[k]);ax.set_title(LABEL[k]);ax.set_xlabel("Operações aguardando antes da submissão");ax.set_ylabel("Espera posterior (ms)");ax.grid(alpha=.2)
    fig.suptitle("C4 — Acúmulo observável na submissão e espera por worker");save(fig,"C","C4_acumulo_espera_dispersao")
    # D2 & E2 HTTP temporal
    for k in ORDER:
        d=runs[k]["http_bins"];fig,ax=plt.subplots(figsize=(11,4));line(ax,k,np.arange(15)*10+5,d.med,label="Mediana",marker="o",ms=3);ax.plot(np.arange(15)*10+5,d.p95,color=COLOR[k],ls="--",marker="^",ms=3,label="p95 (n≥20)");shade(ax);ax.set_ylabel("Duração HTTP (ms)");ax.legend();ax.set_title(f"D2 — Duração HTTP por janela de 10 s: {LABEL[k]}");save(fig,"D",f"D2_duracao_temporal_{k}")
    def http_render(ax,k):
        d=runs[k]["http_bins"];ax.plot(np.arange(15)*10+5,d.med,color=COLOR[k],label="Mediana");ax.plot(np.arange(15)*10+5,d.p95,color=COLOR[k],ls="--",label="p95")
    lim=(0,max(d["http_bins"].p95.max() for d in runs.values())*1.1)
    matrix("D","D2_duracao_temporal","D2 — Duração HTTP por janelas de 10 s","Duração HTTP (ms)",http_render,lim)
    matrix("E","E2_duracao_http","E2 — Duração HTTP por janelas de 10 s","Duração HTTP (ms)",http_render,lim)
    fig,ax=plt.subplots(figsize=(12,5))
    for k in ORDER:line(ax,k,np.arange(15)*10+5,runs[k]["http_bins"].med,LABEL[k],marker="o",ms=3)
    shade(ax);ax.set_ylabel("Mediana da duração HTTP (ms)");ax.legend(ncol=2,loc="upper center",bbox_to_anchor=(.5,-.17));ax.set_title("D2 — Mediana da duração HTTP por janelas de 10 s");save(fig,"D","D2_duracao_temporal_comparativo")
    # D4 outcomes
    categories=["Sucesso 2xx","Erro HTTP","Timeout","Falha de conexão","Outro"]
    outcomes=[]
    for k in ORDER:
        d=runs[k]["main_req"];c=Counter()
        for row in d.itertuples():
            if row.outcome=="response": c["Sucesso 2xx" if 200<=row.http_status<=299 else "Erro HTTP"]+=1
            elif "timeout" in str(row.outcome).lower() or "timeout" in str(row.error_type).lower():c["Timeout"]+=1
            elif "connect" in str(row.error_type).lower():c["Falha de conexão"]+=1
            else:c["Outro"]+=1
        assert sum(c.values())==len(d);outcomes.append(c)
    fig,ax=plt.subplots(figsize=(10,5));totals=[sum(c.values()) for c in outcomes]
    ax.bar(range(4),totals,color=[COLOR[k] for k in ORDER],hatch="//")
    for i,n in enumerate(totals):ax.text(i,n+75,f"{n} (100%)",ha="center",fontsize=10)
    ax.set_ylim(0,max(totals)*1.12);ax.set_xticks(range(4),ORDER);ax.set_ylabel("Respostas HTTP 2xx; início em [30,150) s");ax.grid(axis="y",alpha=.2)
    ax.set_title("D4 — Respostas HTTP 2xx nas quatro configurações\nErros HTTP, timeouts e outros encerramentos: zero");save(fig,"D","D4_desfechos_http")
    # E1 integrated panels, six tracks to avoid mixed units.
    for k in ORDER:
        d=runs[k];x,w,r=d["steps"];fig,axes=plt.subplots(6,1,figsize=(12,13),sharex=True)
        axes[0].step(np.arange(150),d["rps"],where="post",color=COLOR[k]);axes[0].set_ylabel("Inícios/s")
        axes[1].plot(d["stats"].t,d["stats"].cpu,color=COLOR[k],marker="o",ms=2);axes[1].set_ylabel("CPU (%)")
        axes[2].plot(d["stats"].t,d["stats"].mem,color=COLOR[k],marker="o",ms=2);axes[2].set_ylabel("Memória (MiB)")
        axes[3].step(x,r,where="post",color=COLOR[k]);axes[3].set_ylabel("Workers ocupados")
        axes[4].step(x,w,where="post",color=COLOR[k]);axes[4].set_ylabel("Operações aguardando")
        axes[5].plot(np.arange(15)*10+5,d["http_bins"].med,color=COLOR[k],label="Mediana");axes[5].plot(np.arange(15)*10+5,d["http_bins"].p95,color=COLOR[k],ls="--",label="p95");axes[5].set_ylabel("Duração HTTP (ms)");axes[5].legend()
        for ax in axes:shade(ax)
        fig.suptitle(f"E1 — Painel temporal integrado: {LABEL[k]}");save(fig,"E",f"E1_painel_integrado_{k}")
    # Persist processed summaries and validations.
    summary=[];validation={"source_sha256":{},"runs":{},"figures":figures}
    for k,d in runs.items():
        req=d["main_req"];good=req[(req.outcome=="response")&req.http_status.between(200,299)];s=d["main_stats"];w=d["main_works"]
        row={"config":k,"sources":d["cfg"]["normal_traffic"]["clients"],"nominal_rps":d["cfg"]["normal_traffic"]["clients"]*d["cfg"]["normal_traffic"]["rate"],"http_started":len(req),"effective_rps":len(req)/120,"success":len(good),"cpu_n":len(s),"cpu_mean":s.cpu.mean(),"cpu_median":s.cpu.median(),"cpu_max":s.cpu.max(),"mem_n":len(s),"mem_mean_mib":s.mem.mean(),"mem_median_mib":s.mem.median(),"mem_max_mib":s.mem.max(),"mem_first_last_delta_mib":d["stats"].mem.iloc[-1]-d["stats"].mem.iloc[0],"worker_wait_n":len(w),"worker_wait_median_ms":w.wait_ms.median(),"worker_wait_p95_ms":w.wait_ms.quantile(.95),"worker_wait_max_ms":w.wait_ms.max(),"http_median_ms":good.duration_ms.median(),"http_mean_ms":good.duration_ms.mean(),"http_p95_ms":good.duration_ms.quantile(.95),"http_max_ms":good.duration_ms.max(),"max_waiting":int(d["steps"][1].max()),"max_running":int(d["steps"][2].max()),"fraction_0_workers":d["fractions"][0],"fraction_1_worker":d["fractions"][1],"fraction_2_workers":d["fractions"][2]}
        summary.append(row)
        validation["source_sha256"].update(d["hashes"])
        validation["runs"][k]={"run_id":d["status"]["run_id"],"request_total":len(d["req"]),"rtt_total":len(d["rtt"]),"work_cycles":len(d["works"]),"source_events":d["sources"],"victim_stats":len(d["stats"]),"clock":d["clock"],"http_start_range_s":[float(d["req"].elapsed_seconds.min()),float(d["req"].elapsed_seconds.max())],"stats_range_s":[float(d["stats"].t.min()),float(d["stats"].t.max())],"outcomes_main":dict(outcomes[ORDER.index(k)]),"http_bin_n":d["http_bins"].n.fillna(0).astype(int).tolist()}
        d["http_bins"].to_csv(OUT/"processed"/f"http_10s_{k}.csv",index_label="janela_10s")
        pd.DataFrame({"t_s":d["steps"][0],"aguardando":d["steps"][1],"em_execucao":d["steps"][2]}).to_csv(OUT/"processed"/f"workers_eventos_{k}.csv",index=False)
        pd.DataFrame({"segundo":np.arange(150),"http_iniciados":d["rps"]}).to_csv(OUT/"processed"/f"rps_1s_{k}.csv",index=False)
    pd.DataFrame(summary).to_csv(OUT/"processed"/"summary.csv",index=False)
    validation["figure_pairs"]=len(figures)//2
    (OUT/"validation"/"checks.json").write_text(json.dumps(validation,indent=2,ensure_ascii=False))
    (OUT/"manifest.json").write_text(json.dumps({"script":"scripts/generate.py","input":str(SRC.relative_to(ROOT)),"main_interval_s":[30,150],"figures":figures,"summary":"processed/summary.csv","validation":"validation/checks.json"},indent=2,ensure_ascii=False))
    print(f"{len(figures)//2} figuras em PNG/PDF; validação: {OUT/'validation/checks.json'}")

if __name__=="__main__":
    for directory in ("processed","validation"):(OUT/directory).mkdir(parents=True,exist_ok=True)
    main()
