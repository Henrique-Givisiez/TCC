# Figuras metodológicas da Seção 4.1

- **Figura 4.1 — Arquitetura do ambiente experimental:** fontes, vítima única, observação durante as execuções e processamento offline.
- **Figura 4.2 — Percurso metodológico da investigação:** exploração, partições da campanha definitiva e dois ramos de avaliação.

Os SVG são fontes vetoriais editáveis; `gerar_figuras.py` reproduz SVG, PDF vetorial e PNG. A alternativa a TikZ foi usada porque não há compilador LaTeX instalado neste ambiente. Para regenerar: `python3 reports/figuras_metodologia/gerar_figuras.py` (requer Matplotlib). Para incluir no Overleaf, use os PDF com `\includegraphics[width=\linewidth]{...}`.
