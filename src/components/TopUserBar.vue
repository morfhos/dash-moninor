<template>
  <div class="top-userbar">
    <div class="top-userbar-left">
      <div class="search">
        <span class="search-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
        </span>
        <input class="search-input" type="text" placeholder="Pesquisar..." />
      </div>
    </div>

    <div class="top-userbar-right">
      <button class="icon-btn" type="button" aria-label="Notificações">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"></path><path d="M13.73 21a2 2 0 0 1-3.46 0"></path></svg>
      </button>
      <button class="icon-btn" type="button" aria-label="Mensagens">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>
      </button>
      <button class="icon-btn" type="button" aria-label="Ações">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="1"></circle><line x1="12" y1="8" x2="12" y2="8"></line><line x1="12" y1="16" x2="12" y2="16"></line></svg>
      </button>

      <div class="divider-vertical"></div>

      <div ref="profileWrap" class="profile-wrap">
        <button class="profile-btn" type="button" @click="toggleMenu">
          <span class="avatar">
            <img v-if="userAvatarUrl" :src="userAvatarUrl" alt="" />
            <span v-else class="avatar-fallback">{{ initials }}</span>
          </span>
          <span class="profile-name">{{ userName }}</span>
          <span class="profile-caret">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
          </span>
        </button>

        <div v-if="menuOpen" class="profile-menu">
          <button class="profile-menu-item" type="button" @click="logout">
            <span class="menu-icon">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
            </span>
            Logout
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'TopUserBar',
  props: {
    userName: { type: String, default: 'Marcio' },
    userAvatarUrl: { type: String, default: '' }
  },
  data() {
    return { menuOpen: false }
  },
  computed: {
    initials() {
      const parts = String(this.userName || '').trim().split(/\s+/).filter(Boolean)
      const a = parts[0]?.[0] || 'U'
      const b = parts[1]?.[0] || ''
      return (a + b).toUpperCase()
    }
  },
  mounted() {
    document.addEventListener('click', this.onDocumentClick, { capture: true })
  },
  beforeUnmount() {
    document.removeEventListener('click', this.onDocumentClick, { capture: true })
  },
  methods: {
    toggleMenu() {
      this.menuOpen = !this.menuOpen
    },
    onDocumentClick(e) {
      const el = this.$refs.profileWrap
      if (!el) return
      if (!el.contains(e.target)) this.menuOpen = false
    },
    logout() {
      localStorage.removeItem('mc_token')
      this.menuOpen = false
      this.$router.replace('/login?redirect=/')
    }
  }
}
</script>

<style scoped>
.profile-wrap {
  position: relative;
}

.profile-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 8px);
  min-width: 180px;
  background: #ffffff;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  box-shadow: var(--shadow-sm);
  padding: 6px;
  z-index: 30;
}

.profile-menu-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 10px;
  border-radius: 10px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.profile-menu-item:hover {
  background: #f8fafc;
}

.menu-icon {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
}
</style>
