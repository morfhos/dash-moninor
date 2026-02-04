<template>
  <div class="topbar">
    <h1>Timeline - Campanhas</h1>
  </div>
  
  <div class="cards">
    <div class="metric purple">
      <div class="icon-box">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
        </svg>
      </div>
      <div>
        <div class="value">R$750,000</div>
        <div class="label">Investimento Total</div>
      </div>
    </div>
    
    <div class="metric blue">
      <div class="icon-box">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <polyline points="12 6 12 12 16 14"></polyline>
        </svg>
      </div>
      <div>
        <div class="value">8 : 8</div>
        <div class="label">Campanhas Ativas</div>
      </div>
    </div>
    
    <div class="metric teal">
      <div class="icon-box">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
          <line x1="16" y1="13" x2="8" y2="13"></line>
          <line x1="16" y1="17" x2="8" y2="17"></line>
          <polyline points="10 9 9 9 8 9"></polyline>
        </svg>
      </div>
      <div>
        <div class="value">R$25,000</div>
        <div class="label">Campanhas Ativas</div>
      </div>
    </div>
    
    <div class="metric cyan">
      <div class="icon-box">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M11 5L6 9H2V15H6L11 19V5Z"></path>
          <path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>
          <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
        </svg>
      </div>
      <div>
        <div class="value">R$25,000</div>
        <div class="label">Investimento Diário</div>
      </div>
    </div>
  </div>
</template>

<script>
export default { name: 'HeaderStats' }
</script>
