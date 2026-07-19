import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 15000,
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

// ---------- 管理员：训练类型 ----------
export const listTrainingTypesAdmin = () => http.get('/admin/training-types')
export const createTrainingType = (data) => http.post('/admin/training-types', data)
export const deleteTrainingType = (id) => http.delete(`/admin/training-types/${id}`)

// ---------- 管理员：语料 ----------
export const listCorpus = (trainingTypeId) =>
  http.get('/admin/corpus', { params: { training_type_id: trainingTypeId } })
export const createCorpus = (data) => http.post('/admin/corpus', data)
export const deleteCorpus = (id) => http.delete(`/admin/corpus/${id}`)

// ---------- 客服：训练 ----------
export const listTrainingTypesAgent = () => http.get('/agent/training-types')
export const startSession = (trainingTypeId) =>
  http.post('/agent/sessions', { training_type_id: trainingTypeId })
export const getSession = (id) => http.get(`/agent/sessions/${id}`)
export const listMessages = (sessionId) =>
  http.get(`/agent/sessions/${sessionId}/messages`)
export const sendMessage = (sessionId, content) =>
  http.post(`/agent/sessions/${sessionId}/messages`, { content })
