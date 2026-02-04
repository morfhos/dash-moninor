<template>
  <div class="layout">
    <Sidebar />
    <main class="content">
      <TopUserBar />
      
      <!-- Campaign Header -->
      <div class="campaign-header">
        <div class="header-top">
        
          <h1 class="campaign-title">SABESP • Campanha de Conscientização</h1>
          <div class="campaign-meta">
            <p>Praças: São Paulo, Litoral + Vale do Paraíba, RMSP + Baixada Santista</p>
            <p>Período: 20/12/2025 a 28/02/2026 • Meio: TV Aberta + PayTV, Rádio, Jornal, Digital</p>
          </div>
          
          <div class="campaign-stats">
            <div class="stat-item">
              <span class="stat-label">Orçamento</span>
              <span class="stat-value">R$ 750.000</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Investido</span>
              <span class="stat-value">R$ 412.500</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Peças</span>
              <span class="stat-value">3 (2 ON / 1 OFF)</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Atualização</span>
              <span class="stat-value">há 2 min</span>
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
          <!-- Card 1 -->
          <div class="piece-card">
            <div class="card-header">
              <div>
                <h3 class="piece-title">CONSCIÊNCIA - BANHO</h3>
                <p class="piece-subtitle">TV Aberta + PayTV + OOH</p>
              </div>
              <span class="status-badge on">ON</span>
            </div>
            <div class="card-image">
              <img src="../img/1.png" alt="Consciência Banho" />
            </div>
            <div class="card-footer">
              <div class="footer-row">
                <div class="footer-item">
                  <span class="footer-label">Formato</span>
                  <span class="footer-value">Estático + Vídeo 15s</span>
                </div>
                <div class="footer-item">
                  <span class="footer-label">Período</span>
                  <span class="footer-value">20/12 a 02/01</span>
                </div>
              </div>
              <div class="footer-row">
                <div class="footer-item">
                  <span class="footer-label">Inserções</span>
                  <span class="footer-value">210</span>
                </div>
                <div class="footer-item">
                  <span class="footer-label">Praças</span>
                  <span class="footer-value">Litoral + Vale</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Card 2 -->
          <div class="piece-card">
            <div class="card-header">
              <div>
                <h3 class="piece-title">CONSCIÊNCIA - QUALIDADE DA ÁGUA</h3>
                <p class="piece-subtitle">TV + Jornal • Institucional</p>
              </div>
              <span class="status-badge on">ON</span>
            </div>
            <div class="card-image">
              <img src="../img/2.png" alt="Qualidade da Água" />
            </div>
            <div class="card-footer">
              <div class="footer-row">
                <div class="footer-item">
                  <span class="footer-label">Formato</span>
                  <span class="footer-value">Estático + Vídeo 30s</span>
                </div>
                <div class="footer-item">
                  <span class="footer-label">Período</span>
                  <span class="footer-value">30/12 a 02/01</span>
                </div>
              </div>
              <div class="footer-row">
                <div class="footer-item">
                  <span class="footer-label">Inserções</span>
                  <span class="footer-value">180</span>
                </div>
                <div class="footer-item">
                  <span class="footer-label">Praças</span>
                  <span class="footer-value">São Paulo</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Card 3 -->
          <div class="piece-card">
            <div class="card-header">
              <div>
                <h3 class="piece-title">CONSCIÊNCIA - ÁGUA BAIXADA</h3>
                <p class="piece-subtitle">Digital • Social + Display</p>
              </div>
              <span class="status-badge off">OFF</span>
            </div>
            <div class="card-image">
              <img src="../img/3.png" alt="Água Baixada" />
            </div>
            <div class="card-footer">
              <div class="footer-row">
                <div class="footer-item">
                  <span class="footer-label">Formato</span>
                  <span class="footer-value">Display + Social</span>
                </div>
                <div class="footer-item">
                  <span class="footer-label">Período</span>
                  <span class="footer-value">06/01 a 31/01</span>
                </div>
              </div>
              <div class="footer-row">
                <div class="footer-item">
                  <span class="footer-label">Impressões</span>
                  <span class="footer-value">2,4M</span>
                </div>
                <div class="footer-item">
                  <span class="footer-label">Praças</span>
                  <span class="footer-value">RMSP + Baixada</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script>
import Sidebar from '../components/Sidebar.vue'
import TopUserBar from '../components/TopUserBar.vue'

export default {
  name: 'CampaignDetail',
  components: { Sidebar, TopUserBar }
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