<template>
  <div class="full-gradient">
    <div class="card" style="width: 380px; padding: 24px;">
      <div style="display:flex; align-items:center; gap:10px; margin-bottom: 6px;">
       <div class="logo-box">
        <img src="../img/logo-sabesp-login.webp" alt="SABESP" />
      </div>
      </div>
      <div style="margin-bottom: 18px;">
        <div style="font-size:22px; font-weight:800; margin-bottom:6px;">Bem-vindo!</div>
        <div style="color:var(--muted)">Acesse sua conta para monitorar suas campanhas em tempo real.</div>
      </div>
      <form @submit.prevent="submit">
        <div style="display:grid; gap:10px; margin-bottom:12px;">
          <input class="input" type="email" v-model.trim="email" placeholder="usuario@email.com" required />
          <input class="input" :type="show ? 'text' : 'password'" v-model="password" placeholder="Sua senha" required />
        </div>
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; color:var(--muted);">
          <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
            <input type="checkbox" v-model="remember" />
            Lembrar de mim
          </label>
          <a href="#" style="text-decoration:none; color:var(--brand-primary);" @click.prevent>Esqueceu a senha?</a>
        </div>
        <button class="btn" style="width:100%" :disabled="loading">
          {{ loading ? 'Entrando...' : 'Entrar' }}
        </button>
      </form>
      <div style="margin-top:14px; font-size:13px; color:var(--muted);">
        Precisa de ajuda? <a href="#" style="color:var(--brand-primary); text-decoration:none">Suporte</a>
      </div>
      <div style="margin-top:8px; font-size:12px; color:#94a3b8">© 2026 BBRO. Todos os direitos reservados.</div>
    </div>
  </div>
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

</style>
<script>
export default {
  name: 'Login',
  data() {
    return {
      email: '',
      password: '',
      remember: true,
      show: false,
      loading: false
    }
  },
  methods: {
    async submit() {
      if (!this.email || !this.password) return
      this.loading = true
      await new Promise(r => setTimeout(r, 600))
      const token = Math.random().toString(36).slice(2)
      localStorage.setItem('mc_token', token)
      const redirect = this.$route.query.redirect || '/'
      this.$router.replace(redirect)
    }
  }
}
</script>
