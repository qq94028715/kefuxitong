import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 120000, // LLM 调用可能较慢，放宽到 2 分钟
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response && err.response.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('role')
      localStorage.removeItem('username')
      if (location.hash !== '#/login') location.hash = '#/login'
    }
    return Promise.reject(err)
  }
)

// ---------- 认证 ----------
export const adminLogin = (data) => http.post('/admin/login', data)
export const agentLogin = (data) => http.post('/agent/login', data)

// ---------- 管理员：客服账号 ----------
export const listAgents = () => http.get('/admin/agents')
export const createAgent = (data) => http.post('/admin/agents', data)
export const deleteAgent = (id) => http.delete(`/admin/agents/${id}`)

// ---------- 分类 ----------
export const listCategoriesAdmin = () => http.get('/admin/categories')
export const listCategoriesAgent = () => http.get('/agent/categories')
export const createCategory = (data) => http.post('/admin/categories', data)
export const deleteCategory = (id) => http.delete(`/admin/categories/${id}`)

// ---------- 材料 ----------
export const listMaterials = (categoryId) =>
  http.get('/admin/materials', { params: { category_id: categoryId } })

export const uploadMaterial = (categoryId, file, quality = 'normal', sourceType = 'sales') => {
  const form = new FormData()
  form.append('category_id', categoryId)
  form.append('quality', quality)
  form.append('source_type', sourceType)
  form.append('file', file)
  return http.post('/admin/materials/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const deleteMaterial = (id) => http.delete(`/admin/materials/${id}`)

export const getMaterial = (id) => http.get(`/admin/materials/${id}`)

export const updateMaterial = (id, data) => http.put(`/admin/materials/${id}`, data)

// ---------- 知识库 ----------
export const getKnowledge = (categoryId) =>
  http.get('/admin/knowledge', { params: { category_id: categoryId } })

export const extractKnowledge = (categoryId) =>
  http.post('/admin/knowledge/extract', { category_id: categoryId })

// ---------- 管理员：训练成绩 ----------
export const listAdminSessions = (params = {}) =>
  http.get('/admin/sessions', { params })

export const getAdminSession = (id) => http.get(`/admin/sessions/${id}`)

// ---------- 客服：训练 ----------
export const startSession = (categoryId) =>
  http.post('/agent/sessions', { category_id: categoryId })

export const getSession = (id) => http.get(`/agent/sessions/${id}`)
export const listMessages = (sessionId) =>
  http.get(`/agent/sessions/${sessionId}/messages`)

export const sendMessage = (sessionId, content) =>
  http.post(`/agent/sessions/${sessionId}/messages`, { content })

/** v0.3 流式消息：SSE 逐字接收
 * onToken(token): 每收到一个字符调用
 * onDone(data): 流结束时调用，data={done:true, message_id, turn, is_finished}
 */
export const streamMessage = (sessionId, content, onToken, onDone) => {
  const token = localStorage.getItem('token')
  return fetch(`/api/agent/sessions/${sessionId}/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ content }),
  }).then(async (res) => {
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '连接失败' }))
      throw new Error(err.detail || '请求失败')
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.done) {
              onDone(data)
              return data
            } else if (typeof onToken === 'function') {
              onToken(data.token || '')
            }
          } catch (_) { /* 忽略解析异常的行 */ }
        }
      }
    }
  });
};

export const finishSession = (sessionId) =>
  http.post(`/agent/sessions/${sessionId}/finish`)

export const getScore = (sessionId) =>
  http.get(`/agent/sessions/${sessionId}/score`)
