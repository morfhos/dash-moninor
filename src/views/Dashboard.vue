<template>
  <div class="layout">
    <Sidebar />
    <main class="content">
      <TopUserBar />
      <HeaderStats />

      <div class="grid">
        <section class="main-panel">
          <div class="panel-header">
            <div class="filters">
              <div class="filter-select">Todas <span>▾</span></div>
              <div class="filter-select">Todas <span>▾</span></div>
              <div class="date-picker">
                <div class="filter-select">Praças <span>▾</span></div>
                Dezembro 20, 2025 – Janeiro 31, 2026
                <span style="opacity: 0.5;">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                    <line x1="16" y1="2" x2="16" y2="6"></line>
                    <line x1="8" y1="2" x2="8" y2="6"></line>
                    <line x1="3" y1="10" x2="21" y2="10"></line>
                  </svg>
                </span>
              </div>
            </div>

            <div class="toolbar">
              <div class="status-indicator">
                <span class="status-dot"></span>
                Atualizado agora
              </div>

              <div class="tool-btn">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path>
                </svg>
              </div>

              <div class="tool-btn">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="6 9 6 2 18 2 18 9"></polyline>
                  <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path>
                  <rect x="6" y="14" width="12" height="8"></rect>
                </svg>
              </div>

              <div class="tool-btn">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                  <circle cx="8.5" cy="8.5" r="1.5"></circle>
                  <polyline points="21 15 16 10 5 21"></polyline>
                </svg>
              </div>

              <div class="tool-btn">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="11" cy="11" r="8"></circle>
                  <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                </svg>
              </div>

              <div class="export-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                  <polyline points="14 2 14 8 20 8"></polyline>
                  <line x1="16" y1="13" x2="8" y2="13"></line>
                  <line x1="16" y1="17" x2="8" y2="17"></line>
                  <polyline points="10 9 9 9 8 9"></polyline>
                </svg>
                EXPORTAR
                <span>▾</span>
              </div>
            </div>
          </div>

          <div class="month-selector">
            <div class="month-item">Dez</div>
            <div class="month-item active">Dezembro 2025</div>
            <div class="month-item">Janeiro</div>
            <div class="year-pill">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                <line x1="16" y1="2" x2="16" y2="6"></line>
                <line x1="8" y1="2" x2="8" y2="6"></line>
                <line x1="3" y1="10" x2="21" y2="10"></line>
              </svg>
              2026
            </div>
          </div>

          <div style="margin-top: 24px;">
            <div class="panel-header" style="margin-bottom: 12px; border-bottom: 1px solid #f1f5f9; padding-bottom: 8px;">
              <h3 style="font-size: 14px; font-weight: 700;">Dezembro</h3>
              <div class="section-tools">
                <span>Dezembro 2025</span>
                <span class="divider">|</span>
                <span class="tool-icon">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                    <line x1="16" y1="2" x2="16" y2="6"></line>
                    <line x1="8" y1="2" x2="8" y2="6"></line>
                    <line x1="3" y1="10" x2="21" y2="10"></line>
                  </svg>
                  23
                </span>
                <span class="tool-icon">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                </span>
                <span class="tool-icon">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2v-2"></path>
                    <rect x="4" y="2" width="8" height="4" rx="1" ry="1"></rect>
                    <path d="M4 6h8v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6z"></path>
                  </svg>
                </span>
                <span class="tool-icon">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="20" x2="18" y2="10"></line>
                    <line x1="12" y1="20" x2="12" y2="4"></line>
                    <line x1="6" y1="20" x2="6" y2="14"></line>
                  </svg>
                </span>
                <span class="tool-icon">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                    <polyline points="14 2 14 8 20 8"></polyline>
                  </svg>
                </span>
              </div>
            </div>

            <!-- TIMELINE -->
            <div class="timeline-container">
              <!-- LINHA DO "AGORA" (overlay) -->
              <div
                class="now-line"
                :style="{ left: nowLeftPercent + '%' }"
                v-show="nowVisible"
              >
                <div class="now-dot"></div>
                <div class="now-time">{{ nowLabel }}</div>
              </div>

              <div class="timeline-grid">
                <div class="timeline-row">
                  <div class="row-info">
                    <span class="row-title">Litoral +</span>
                    <span class="row-subtitle">- Vale taraba</span>
                  </div>
                  <div class="row-content">
                    <div class="timeline-bar" @click="$router.push('/campaign/1')" style="background: var(--bar-orange); width: 25%; margin-left: 5%;">
                      <span class="bar-title">Filme Verão Obras 60"</span>
                      <span class="bar-dates">20/12 a 02/01</span>
                    </div>
                    <div class="timeline-bar" @click="$router.push('/campaign/1')" style="background: var(--bar-blue); width: 30%; margin-left: 15%;">
                      <span class="bar-title">Filme Verão Obras 30"</span>
                      <span class="bar-dates">20/12 a 02/01</span>
                    </div>
                    <div class="timeline-bar" @click="$router.push('/campaign/1')" style="background: var(--bar-yellow); width: 20%;">
                      <span class="bar-title">Filme Verão Obras 30"</span>
                    </div>
                  </div>
                </div>

                <div class="timeline-row">
                  <div class="row-info">
                    <span class="row-title">São Paulo</span>
                  </div>
                  <div class="row-content">
                    <div class="timeline-bar" @click="$router.push('/campaign/1')" style="background: var(--bar-yellow); width: 30%; margin-left: 10%;">
                      <span class="bar-title">Texto Verão Obras 30"</span>
                      <span class="bar-dates">20/12 a 28/12</span>
                    </div>
                    <div class="timeline-bar" @click="$router.push('/campaign/1')" style="background: var(--bar-blue); width: 35%; margin-left: 10%;">
                      <span class="bar-title">Filme Comunicado</span>
                      <span class="bar-dates">20/12 a 28/12</span>
                    </div>
                  </div>
                </div>

                <div class="timeline-row">
                  <div class="row-info">
                    <span class="row-title">RMSP</span>
                    <span class="row-subtitle">- Baixada Santista</span>
                  </div>
                  <div class="row-content">
                    <div class="timeline-bar" @click="$router.push('/campaign/1')" style="background: var(--bar-green); width: 20%; margin-left: 5%;">
                      <span class="bar-title">Filme Verão Obras 60"</span>
                      <span class="bar-dates">22/12 a 26/12</span>
                    </div>
                    <div class="timeline-bar" @click="$router.push('/campaign/1')" style="background: var(--bar-yellow); width: 25%; margin-left: 5%;">
                      <span class="bar-title">Filme Verão Obras 30"</span>
                      <span class="bar-dates">22/12 a 31/01</span>
                    </div>
                    <div class="timeline-bar" @click="$router.push('/campaign/1')" style="background: var(--bar-blue); width: 15%; margin-left: 5%;">
                      <span class="bar-title">Spot Verão Obras 30"</span>
                      <span class="bar-dates">22/12 a 31/01</span>
                    </div>
                  </div>
                </div>

                <div class="timeline-row">
                  <div class="row-info">
                    <span class="row-title">Rádio</span>
                  </div>
                  <div class="row-content">
                    <div class="timeline-bar" @click="$router.push('/campaign/1')" style="background: var(--bar-orange); width: 25%; margin-left: 5%;">
                      <span class="bar-title">Filme Verão Obras 30"</span>
                      <span class="bar-dates">20/12 a 26/16</span>
                    </div>
                    <div class="timeline-bar" @click="$router.push('/campaign/1')" style="background: var(--bar-blue); width: 20%; margin-left: 10%;">
                      <span class="bar-title">Verão Obras 30"</span>
                      <span class="bar-dates">20/12 a 26/16</span>
                    </div>
                  </div>
                </div>

                <div class="timeline-row">
                  <div class="row-info">
                    <span class="row-title">Jornal</span>
                  </div>
                  <div class="row-content">
                    <div class="timeline-bar" @click="$router.push('/campaign/1')" style="background: var(--bar-green); width: 30%; margin-left: 5%;">
                      <span class="bar-title">Filme Verão Obras 30"</span>
                      <span class="bar-dates">20/12 a 24/12</span>
                    </div>
                    <div class="timeline-bar" @click="$router.push('/campaign/1')" style="background: var(--bar-blue); width: 15%; margin-left: 5%;">
                      <span class="bar-title">Projecao Verão</span>
                    </div>
                    <div class="timeline-bar" @click="$router.push('/campaign/1')" style="background: var(--bar-blue); width: 35%; margin-left: 10%;">
                      <span class="bar-title">Anúncios de Verão, 30/01 a 28/02</span>
                    </div>
                  </div>
                </div>

                <div class="timeline-row">
                  <div class="row-info">
                    <span class="row-title">Projetos</span>
                  </div>
                  <div class="row-content" style="gap: 4px;">
                    <div style="background: #FF9800; color: white; padding: 2px 4px; border-radius: 2px; font-size: 8px; font-weight: 700;">RMSF</div>
                    <div style="background: #FF9800; color: white; padding: 2px 4px; border-radius: 2px; font-size: 8px; font-weight: 700;">PrsSP</div>
                    <div style="background: #03A9F4; color: white; padding: 2px 4px; border-radius: 2px; font-size: 8px; font-weight: 700;">RMSF</div>
                    <span style="font-size: 10px; color: var(--text-secondary); margin-left: 4px;">10/01 a 22/02</span>
                  </div>
                </div>
              </div>
            </div>
            <!-- /TIMELINE -->
          </div>
        </section>

        <aside class="aside-panel">
          <section class="chart-section">
            <h3 class="section-title">Investimento por Região</h3>
            <div style="position: relative;">
              <DonutChart
                centerText="Litoral + Vale do Paraíba"
                :segments="[
                  { value: 34, color: '#8b5cf6' },
                  { value: 15, color: '#f87171' },
                  { value: 15, color: '#fbbf24' },
                  { value: 15, color: '#3b82f6' },
                  { value: 21, color: '#dcfce7' }
                ]"
              />
            </div>
            <ul class="legend" style="margin-top: 24px;">
              <li style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="width: 10px; height: 10px; border-radius: 2px; background: #f87171;"></span>
                  <span style="font-size: 13px; color: var(--text-secondary);">São Paulo</span>
                </div>
                <span style="font-weight: 600; font-size: 13px;">34%</span>
              </li>
              <li style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="width: 10px; height: 10px; border-radius: 2px; background: #fbbf24;"></span>
                  <span style="font-size: 13px; color: var(--text-secondary);">RMSF)</span>
                </div>
                <span style="font-weight: 600; font-size: 13px;">15%</span>
              </li>
              <li style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="width: 10px; height: 10px; border-radius: 2px; background: #3b82f6;"></span>
                  <span style="font-size: 13px; color: var(--text-secondary);">RMSP + Baixada Santista</span>
                </div>
                <span style="font-weight: 600; font-size: 13px;">15%</span>
              </li>
              <li style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="width: 10px; height: 10px; border-radius: 2px; background: #dcfce7;"></span>
                  <span style="font-size: 13px; color: var(--text-secondary);">Outros</span>
                </div>
                <span style="font-weight: 600; font-size: 13px;">9%</span>
              </li>
            </ul>
          </section>

          <section class="activities-section">
            <h3 class="section-title">Atividades Recentes</h3>
            <ul style="list-style: none; display: flex; flex-direction: column; gap: 12px;">
              <li style="display: flex; gap: 10px; align-items: flex-start;">
                <div style="width: 18px; height: 18px; border-radius: 4px; background: #fbbf24; display: flex; align-items: center; justify-content: center; color: white; font-size: 10px;">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                    <polyline points="14 2 14 8 20 8"></polyline>
                    <line x1="16" y1="13" x2="8" y2="13"></line>
                    <line x1="16" y1="17" x2="8" y2="17"></line>
                    <polyline points="10 9 9 9 8 9"></polyline>
                  </svg>
                </div>
                <div>
                  <div style="font-weight: 600; font-size: 13px;">Filme Verão Obras 60</div>
                  <div style="font-size: 11px; color: var(--text-secondary);">TV aberta + Pay TV</div>
                </div>
              </li>

              <li style="display: flex; gap: 10px; align-items: flex-start;">
                <div style="width: 18px; height: 18px; border-radius: 4px; background: #8b5cf6; display: flex; align-items: center; justify-content: center; color: white; font-size: 10px;">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M11 5L6 9H2V15H6L11 19V5Z"></path>
                    <path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>
                    <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
                  </svg>
                </div>
                <div>
                  <div style="font-weight: 600; font-size: 13px;">Spot Verão Obras 30</div>
                  <div style="font-size: 11px; color: var(--text-secondary);">26/24</div>
                </div>
              </li>

              <li style="display: flex; gap: 10px; align-items: flex-start;">
                <div style="width: 18px; height: 18px; border-radius: 4px; background: #22c55e; display: flex; align-items: center; justify-content: center; color: white; font-size: 10px;">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
                    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
                  </svg>
                </div>
                <div>
                  <div style="font-weight: 600; font-size: 13px;">Anúncios de Jornal</div>
                  <div style="font-size: 11px; color: var(--text-secondary);">20/12 a 13/01</div>
                </div>
              </li>
            </ul>
          </section>
        </aside>
      </div>
    </main>
  </div>
</template>

<script>
import Sidebar from '../components/Sidebar.vue'
import TopUserBar from '../components/TopUserBar.vue'
import HeaderStats from '../components/HeaderStats.vue'
import DonutChart from '../components/DonutChart.vue'

export default {
  name: 'Dashboard',
  components: { Sidebar, TopUserBar, HeaderStats, DonutChart },

  data() {
    return {
      // ===== LINHA DO "AGORA" =====
      nowLeftPercent: 0,
      nowLabel: '',
      nowVisible: true,
      nowTimer: null,

      // Janela de tempo do demo (você pode mudar)
      // Exemplo: 14:00–18:00 (combina com o print de programação)
      timelineStart: '14:00',
      timelineEnd: '18:00'
    }
  },

  mounted() {
    this.updateNowLine()
    this.nowTimer = setInterval(this.updateNowLine, 30 * 1000) // atualiza a cada 30s
  },

  // compatibilidade Vue2/Vue3
  beforeDestroy() {
    clearInterval(this.nowTimer)
  },
  beforeUnmount() {
    clearInterval(this.nowTimer)
  },

  methods: {
    parseHHMM(hhmm) {
      const [h, m] = hhmm.split(':').map(Number)
      return h * 60 + m
    },
    pad2(n) {
      return String(n).padStart(2, '0')
    },
    updateNowLine() {
      const now = new Date()
      const nowMin = now.getHours() * 60 + now.getMinutes()

      const startMin = this.parseHHMM(this.timelineStart)
      const endMin = this.parseHHMM(this.timelineEnd)

      this.nowLabel = `${this.pad2(now.getHours())}:${this.pad2(now.getMinutes())}`

      // Se estiver fora da janela do timeline, escondemos (demo)
      // Se preferir "travar na borda", eu ajusto pra clamp.
      if (nowMin < startMin || nowMin > endMin) {
        this.nowVisible = false
        return
      }
      this.nowVisible = true

      const progress = (nowMin - startMin) / (endMin - startMin)
      const percent = Math.max(0, Math.min(100, progress * 100))
      this.nowLeftPercent = percent
    }
  }
}
</script>

<style>
/* =========================
   STATUS "RADAR" (AO VIVO)
========================= */
.status-indicator{
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  padding: 6px 10px;
  border-radius: 999px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.status-dot{
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #ff3b57;
  position: relative;
  box-shadow: 0 0 0 2px rgba(255,59,87,.12);
}

.status-dot::before,
.status-dot::after{
  content: "";
  position: absolute;
  inset: -10px;
  border-radius: 999px;
  border: 2px solid rgba(255,59,87,.35);
  transform: scale(.3);
  opacity: 0;
  animation: radarPulse 1.6s ease-out infinite;
}

.status-dot::after{
  inset: -16px;
  border-color: rgba(255,59,87,.22);
  animation-delay: .8s;
}

@keyframes radarPulse{
  0%   { transform: scale(.25); opacity: .0; }
  15%  { opacity: .75; }
  100% { transform: scale(1); opacity: 0; }
}

@media (prefers-reduced-motion: reduce){
  .status-dot::before,
  .status-dot::after{ animation: none; opacity: .35; transform: scale(1); }
}

/* =========================
   LINHA DO "AGORA" (TIMELINE)
========================= */
.timeline-container{
  position: relative;
}

/* linha vertical */
.now-line{
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: #ff3b57;
  z-index: 50;
  pointer-events: none;
  transform: translateX(-1px);
  box-shadow: 0 0 0 1px rgba(255,59,87,.08);
}

/* bolinha no topo */
.now-dot{
  position: absolute;
  top: -6px;
  left: 50%;
  width: 10px;
  height: 10px;
  border-radius: 999px;
  transform: translateX(-50%);
  background: #fff;
  border: 2px solid #ff3b57;
  box-shadow: 0 10px 22px rgba(255,59,87,.18);
}

.now-time{
  position: absolute;
  top: -22px;
  left: 8px;
  font-size: 11px;
  font-weight: 800;
  color: #ff3b57;
  background: rgba(255,255,255,.92);
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid rgba(255,59,87,.25);
  white-space: nowrap;
}
</style>
