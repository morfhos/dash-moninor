<template>
  <div class="layout">
    <Sidebar />
    <main class="content">
      <TopUserBar />
      
      <!-- Campaign Header -->
      <div class="campaign-header">
        <div class="header-top">
        
          <h1 class="campaign-title">{{ headerTitle }}</h1>
          <div class="campaign-meta">
            <p v-if="campaign && campaign.markets && campaign.markets.length">Praças: {{ campaign.markets.join(', ') }}</p>
            <p v-if="campaign">
              Período: {{ formatDateRange(campaign.period.start, campaign.period.end) }} • Meio: {{ (campaign.media && campaign.media.channels ? campaign.media.channels : []).join(', ') }}
            </p>
            <p v-if="loading">Carregando campanha...</p>
            <p v-if="error" style="color:#b91c1c; font-weight: 700;">{{ error }}</p>
          </div>
          
          <div class="campaign-stats" v-if="campaign">
            <div class="stat-item">
              <span class="stat-label">Orçamento</span>
              <span class="stat-value">{{ formatCurrency(campaign.budget_total) }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Investido</span>
              <span class="stat-value">{{ formatCurrency(campaign.metrics && campaign.metrics.cost) }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Peças</span>
              <span class="stat-value">{{ piecesText }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Atualização</span>
              <span class="stat-value">{{ updatedText }}</span>
            </div>
          </div>
        </div>
        
        <div class="campaign-tabs">
          <button class="tab-btn">Visão Geral</button>
          <button class="tab-btn active">Peças</button>
          <button class="tab-btn">Veiculação</button>
          <button class="tab-btn">Relatórios</button>
          <button class="tab-btn">Anexos</button>
        </div>
      </div>

      <!-- Campaign Content -->
      <div class="campaign-content">
        <div class="content-header">
        <button class="back-btn" @click="$router.push('/')">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="19" y1="12" x2="5" y2="12"></line>
              <polyline points="12 19 5 12 12 5"></polyline>
            </svg>
            <span>Voltar</span>
          </button>
          <h2 class="section-title">Peças da Campanha</h2>
        </div>

        <div class="pieces-grid">
          <div v-if="!loading && campaign && campaign.pieces && campaign.pieces.length" v-for="p in campaign.pieces" :key="p.id" class="piece-card">
            <div class="card-header">
              <div>
                <h3 class="piece-title">{{ p.title }}</h3>
                <p class="piece-subtitle">{{ p.subtitle }}</p>
              </div>
              <span class="status-badge" :class="badgeClass(p.badge)">{{ p.badge || '-' }}</span>
            </div>
            <div class="card-image">
              <img :src="p.image_url || placeholderImage" :alt="p.title" />
            </div>
            <div class="card-footer">
              <div class="footer-row">
                <div class="footer-item">
                  <span class="footer-label">Formato</span>
                  <span class="footer-value">{{ formatPieceFormat(p) }}</span>
                </div>
                <div class="footer-item">
                  <span class="footer-label">Período</span>
                  <span class="footer-value">{{ formatDateRange(p.period && p.period.start, p.period && p.period.end) }}</span>
                </div>
              </div>
              <div class="footer-row">
                <div class="footer-item">
                  <span class="footer-label">{{ metricLabel(p) }}</span>
                  <span class="footer-value">{{ metricValue(p) }}</span>
                </div>
                <div class="footer-item">
                  <span class="footer-label">Praças</span>
                  <span class="footer-value">{{ (p.markets || []).join(', ') }}</span>
                </div>
              </div>
            </div>
          </div>
          <div v-if="!loading && campaign && (!campaign.pieces || campaign.pieces.length === 0)" style="color:#6B7280; font-weight: 600;">
            Nenhuma peça encontrada para esta campanha.
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script>
import Sidebar from '../components/Sidebar.vue'
import TopUserBar from '../components/TopUserBar.vue'
import placeholderImage from '../img/1.png'

export default {
  name: 'CampaignDetail',
  components: { Sidebar, TopUserBar },
  data() {
    return {
      loading: true,
      error: '',
      campaign: null,
      placeholderImage
    }
  },
  computed: {
    headerTitle() {
      if (!this.campaign) return 'Campanha'
      return `${this.campaign.cliente.nome} • ${this.campaign.name}`
    },
    piecesText() {
      if (!this.campaign || !this.campaign.pieces_stats) return '-'
      const t = this.campaign.pieces_stats.total
      const on = this.campaign.pieces_stats.on
      const off = this.campaign.pieces_stats.off
      return `${t} (${on} ON / ${off} OFF)`
    },
    updatedText() {
      if (!this.campaign || !this.campaign.updated_at) return '-'
      return this.timeAgo(this.campaign.updated_at)
    }
  },
  mounted() {
    this.load()
  },
  watch: {
    '$route.params.id': function () {
      this.load()
    }
  },
  methods: {
    async load() {
      this.loading = true
      this.error = ''
      this.campaign = null
      const id = this.$route.params.id
      try {
        const resp = await fetch(`/api/campaigns/${id}/`, { credentials: 'include' })
        if (resp.status === 401) {
          this.$router.push({ name: 'login', query: { redirect: this.$route.fullPath } })
          return
        }
        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`)
        }
        this.campaign = await resp.json()
      } catch (e) {
        this.error = 'Falha ao carregar os dados da campanha.'
      } finally {
        this.loading = false
      }
    },
    badgeClass(badge) {
      if (badge === 'ON') return 'on'
      if (badge === 'OFF') return 'off'
      return 'off'
    },
    formatDateRange(startIso, endIso) {
      const start = this.parseDate(startIso)
      const end = this.parseDate(endIso)
      if (!start || !end) return '-'
      const s = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(start)
      const e = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(end)
      return `${s} a ${e}`
    },
    parseDate(iso) {
      if (!iso) return null
      const d = new Date(iso)
      if (isNaN(d.getTime())) return null
      return d
    },
    formatCurrency(value) {
      if (value === null || value === undefined || value === '') return '-'
      const n = Number(value)
      if (isNaN(n)) return '-'
      return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(n)
    },
    formatPieceFormat(p) {
      if (!p) return '-'
      const dur = p.duration_sec ? `${p.duration_sec}s` : ''
      const t = (p.type || '').toUpperCase()
      return [t, dur].filter(Boolean).join(' ')
    },
    metricLabel(p) {
      if (p && p.metrics && p.metrics.impressions) return 'Impressões'
      return 'Inserções'
    },
    metricValue(p) {
      if (!p || !p.metrics) return '-'
      if (p.metrics.impressions) return this.formatCompactNumber(p.metrics.impressions)
      return String(p.metrics.insertions || 0)
    },
    formatCompactNumber(n) {
      const num = Number(n)
      if (isNaN(num)) return '-'
      return new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 }).format(num)
    },
    timeAgo(iso) {
      const d = this.parseDate(iso)
      if (!d) return '-'
      const diffMs = Date.now() - d.getTime()
      const mins = Math.floor(diffMs / 60000)
      if (mins < 1) return 'agora'
      if (mins < 60) return `há ${mins} min`
      const hours = Math.floor(mins / 60)
      if (hours < 24) return `há ${hours} h`
      const days = Math.floor(hours / 24)
      return `há ${days} d`
    }
  }
}
</script>

<style scoped>
.campaign-header {
  background-color: #E0E7FF; /* Lilás claro/Lavanda */
  padding: 24px 32px 0;
  border-radius: 8px 8px 0 0;
  margin-bottom: 24px;
}

.header-top {
  margin-bottom: 24px;
}

.back-nav {
  margin-bottom: 12px;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  transition: color 0.2s;
  background: #1e1b4b;
  border-radius: 50px;
  padding: 5px 10px;
}

.back-btn:hover {
  color: #ccc;
}

.campaign-title {
  font-size: 24px;
  font-weight: 700;
  color: #1F2937;
  margin-bottom: 8px;
}

.campaign-meta {
  color: #4B5563;
  font-size: 14px;
  line-height: 1.5;
  margin-bottom: 16px;
}

.campaign-stats {
  display: flex;
  gap: 24px;
  background: rgba(255, 255, 255, 0.5);
  padding: 12px;
  border-radius: 8px;
  display: inline-flex;
}

.stat-item {
  display: flex;
  flex-direction: column;
}

.stat-label {
  font-size: 12px;
  color: #6B7280;
  text-transform: uppercase;
  font-weight: 600;
}

.stat-value {
  font-size: 14px;
  font-weight: 700;
  color: #111827;
}

.campaign-tabs {
  display: flex;
  gap: 8px;
}

.tab-btn {
  padding: 10px 20px;
  border: none;
  background: transparent;
  font-size: 14px;
  font-weight: 500;
  color: #4B5563;
  cursor: pointer;
  border-radius: 20px 20px 0 0;
  transition: all 0.2s;
}

.tab-btn.active {
  background: #1E1B4B; /* Azul escuro/Roxo */
  color: white;
}

.tab-btn:hover:not(.active) {
  background: rgba(255, 255, 255, 0.5);
}

.campaign-content {
  padding: 0 8px;
}

.section-title {
  font-size: 18px;
  font-weight: 700;
  color: #1F2937;
  background-color: #E0E7FF;
  display: inline-block;
  padding: 4px 12px;
  border-radius: 4px;
  margin-bottom: 0;
}

.content-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.pieces-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 24px;
}

.piece-card {
  background: white;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
  border: 1px solid #E5E7EB;
}

.card-header {
  padding: 16px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.piece-title {
  font-size: 14px;
  font-weight: 700;
  color: #111827;
  margin-bottom: 4px;
}

.piece-subtitle {
  font-size: 12px;
  color: #6B7280;
}

.status-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 12px;
  color: white;
}

.status-badge.on {
  background-color: #10B981;
}

.status-badge.off {
  background-color: #9CA3AF;
}

.card-image {
  width: 100%;
  height: 200px;
  overflow: hidden;
  background: #F3F4F6;
  display: flex;
  align-items: center;
  justify-content: center;
}

.card-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.card-footer {
  padding: 16px;
  background: #F9FAFB;
  border-top: 1px solid #E5E7EB;
}

.footer-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
}

.footer-row:last-child {
  margin-bottom: 0;
}

.footer-item {
  display: flex;
  flex-direction: column;
}

.footer-label {
  font-size: 11px;
  color: #9CA3AF;
  margin-bottom: 2px;
}

.footer-value {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}
</style>
