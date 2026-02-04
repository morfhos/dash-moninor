<template>
  <aside class="sidebar">
    <div class="brand">
      <div class="logo-box">
        <img src="../img/logo-sabesp.webp" alt="SABESP" />
      </div>
    </div>

    <nav class="nav">
      <RouterLink to="/" exact-active-class="active" class="menu-item has-submenu">
        <div class="item-content">
          <span class="icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>
          </span>
          <span>Dashboard</span>
        </div>
        <span class="arrow">▼</span>
      </RouterLink>

      <RouterLink to="/" exact-active-class="active" class="menu-item">
        <div class="item-content">
          <span class="icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
          </span>
          <span>Timeline Campanhas</span>
        </div>
      </RouterLink>

      <RouterLink to="/" exact-active-class="active" class="menu-item">
        <div class="item-content">
          <span class="icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>
          </span>
          <span>Relatórios</span>
        </div>
      </RouterLink>

      <RouterLink to="/" exact-active-class="active" class="menu-item">
        <div class="item-content">
          <span class="icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"></path><path d="M22 12A10 10 0 0 0 12 2v10z"></path></svg>
          </span>
          <span>Analytics</span>
        </div>
      </RouterLink>

      <RouterLink to="/" exact-active-class="active" class="menu-item">
        <div class="item-content">
          <span class="icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
          </span>
          <span>Administração</span>
        </div>
      </RouterLink>

      
    </nav>

    <div class="sidebar-footer">
      <button class="logout-btn" type="button" @click="logout">
        <span class="icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
        </span>
        <span>Sair</span>
      </button>
      <div class="version-badge">V1.3.0</div>
    </div>
  </aside>
</template>

<style scoped>
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 4px;
  margin-bottom: 32px;
  font-weight: 600;
  font-size: 18px;
}

.logo-box {
  width: 100%;
  padding: 0 20%;
}

.logo-box img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-label {
  font-size: 11px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.4);
  margin: 20px 0 8px 12px;
  letter-spacing: 1px;
}

.menu-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 8px;
  text-decoration: none;
  color: rgba(255, 255, 255, 0.7);
  font-size: 14px;
  transition: all 0.2s;
}

.item-content {
  display: flex;
  align-items: center;
  gap: 12px;
}

.menu-item:hover {
  background: rgba(255, 255, 255, 0.1);
  color: white;
}

.menu-item.active {
  background: var(--brand-primary);
  color: white;
  box-shadow: 0 4px 12px rgba(93, 59, 227, 0.3);
}

.icon {
  font-size: 16px;
  width: 20px;
  display: flex;
  justify-content: center;
}

.arrow {
  font-size: 10px;
  opacity: 0.5;
}

.sidebar-footer {
  margin-top: auto;
  padding-top: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.logout-btn {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.78);
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
}

.logout-btn:hover {
  background: rgba(255, 255, 255, 0.12);
  color: white;
}

.version-badge {
  background: rgba(255, 255, 255, 0.15);
  color: rgba(255, 255, 255, 0.8);
  padding: 4px 12px;
  border-radius: 99px;
  font-size: 10px;
  width: fit-content;
}
</style>

<script>
export default {
  name: 'Sidebar',
  methods: {
    logout() {
      localStorage.removeItem('mc_token')
      this.$router.replace('/login?redirect=/')
    }
  }
}
</script>
