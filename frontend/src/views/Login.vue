<template>
  <div class="login-wrap">
    <div class="card login-card">
      <h2>客服训练系统</h2>
      <div class="sub">AI 驱动的客服培训平台</div>

      <div class="tabs" style="margin-bottom: 16px">
        <div class="tab" :class="{ active: role === 'admin' }" @click="role = 'admin'">管理员登录</div>
        <div class="tab" :class="{ active: role === 'agent' }" @click="role = 'agent'">客服登录</div>
      </div>

      <div v-if="error" class="error-text">{{ error }}</div>

      <div class="field">
        <label>用户名</label>
        <input
          class="input"
          v-model="form.username"
          placeholder="请输入用户名"
          @keyup.enter="onSubmit"
        />
      </div>
      <div class="field">
        <label>密码</label>
        <input
          class="input"
          type="password"
          v-model="form.password"
          placeholder="请输入密码"
          @keyup.enter="onSubmit"
        />
      </div>

      <button class="btn" style="width: 100%" :disabled="loading" @click="onSubmit">
        {{ loading ? '登录中...' : '登录' }}
      </button>

      <div class="switch-role" v-if="role === 'admin'">
        默认管理员账号：admin / admin123
      </div>
      <div class="switch-role" v-else>
        客服账号由管理员在后台创建
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { adminLogin, agentLogin } from '../api.js'

const router = useRouter()
const role = ref('admin')
const loading = ref(false)
const error = ref('')
const form = reactive({ username: '', password: '' })

async function onSubmit() {
  error.value = ''
  if (!form.username || !form.password) {
    error.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  try {
    const fn = role.value === 'admin' ? adminLogin : agentLogin
    const { data } = await fn({ username: form.username, password: form.password })
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('role', data.role)
    localStorage.setItem('username', data.username)
    router.push(data.role === 'admin' ? '/admin' : '/train')
  } catch (e) {
    error.value = e.response?.data?.detail || '登录失败，请重试'
  } finally {
    loading.value = false
  }
}
</script>
