<template>
  <div>
    <div class="topbar">
      <div class="brand">客服训练系统 · 管理后台</div>
      <div class="actions">
        <span>{{ username }}</span>
        <button class="btn ghost sm" @click="logout">退出</button>
      </div>
    </div>

    <div class="container">
      <div class="card">
        <div class="tabs">
          <div class="tab" :class="{ active: tab === 'agents' }" @click="tab = 'agents'">客服账号</div>
          <div class="tab" :class="{ active: tab === 'cats' }" @click="tab = 'cats'">训练分类</div>
          <div class="tab" :class="{ active: tab === 'mat' }" @click="tab = 'mat'">材料与知识库</div>
          <div class="tab" :class="{ active: tab === 'scores' }" @click="onTabScores">训练成绩</div>
          <div class="tab" :class="{ active: tab === 'trend' }" @click="onTabTrend">成绩趋势</div>
          <div class="tab" :class="{ active: tab === 'batches' }" @click="onTabBatches">训练管理</div>
          <div class="tab" :class="{ active: tab === 'questions' }" @click="onTabQuestions">题库管理</div>
          <div class="tab" :class="{ active: tab === 'mastery' }" @click="onTabMastery">掌握度</div>
          <div class="tab" :class="{ active: tab === 'quick' }" @click="onTabQuick">快捷短语</div>
          <div class="tab" :class="{ active: tab === 'import' }" @click="tab = 'import'">导入语料</div>
        </div>

        <!-- 客服账号 -->
        <div v-if="tab === 'agents'">
          <div class="page-title">客服账号管理</div>
          <div class="page-sub">新增客服账号，供客服登录训练使用</div>
          <div class="row" style="margin-bottom: 16px">
            <input class="input" v-model="agentForm.username" placeholder="客服用户名" />
            <input class="input" v-model="agentForm.password" placeholder="密码" type="password" />
            <button class="btn" style="flex: 0 0 auto" @click="onCreateAgent">新增</button>
          </div>
          <table v-if="agents.length">
            <thead>
              <tr><th>ID</th><th>用户名</th><th>创建时间</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="a in agents" :key="a.id">
                <td>{{ a.id }}</td>
                <td>{{ a.username }}</td>
                <td>{{ fmt(a.created_at) }}</td>
                <td><button class="btn danger sm" @click="onDeleteAgent(a.id)">删除</button></td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty">暂无客服账号，请在上方新增</div>
        </div>

        <!-- 训练分类 -->
        <div v-if="tab === 'cats'">
          <div class="page-title">训练分类管理</div>
          <div class="page-sub">客服登录后可选择不同分类进行训练。每个分类需上传材料并提取知识后才能用于训练。</div>
          <div class="row" style="margin-bottom: 16px">
            <input class="input" v-model="catForm.name" placeholder="分类名称，如：PVC训练" />
            <input class="input" v-model="catForm.description" placeholder="描述（可选）" />
            <button class="btn" style="flex: 0 0 auto" @click="onCreateCat">新增</button>
          </div>
          <table v-if="cats.length">
            <thead>
              <tr><th>ID</th><th>名称</th><th>描述</th><th>材料数</th><th>知识库</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="c in cats" :key="c.id">
                <td>{{ c.id }}</td>
                <td>{{ c.name }}</td>
                <td class="muted">{{ c.description || '-' }}</td>
                <td><span class="tag">{{ c.material_count }} 个</span></td>
                <td>
                  <span v-if="c.knowledge_version" class="tag ok">v{{ c.knowledge_version }}</span>
                  <span v-else class="tag warn">未提取</span>
                </td>
                <td><button class="btn danger sm" @click="onDeleteCat(c.id)">删除</button></td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty">暂无训练分类</div>
        </div>

        <!-- 材料与知识库 -->
        <div v-if="tab === 'mat'">
          <div class="page-title">材料与知识库</div>
          <div class="page-sub">
            上传聊天记录/产品资料（txt、md），系统自动用 AI 提炼为结构化知识库，供模拟客户与评分使用。
            <span class="muted">{{ llmHint }}</span>
          </div>

          <div class="field">
            <label>选择训练分类</label>
            <select class="input" v-model="matCatId" @change="onCatChange">
              <option v-for="c in cats" :key="c.id" :value="c.id">
                {{ c.name }}（{{ c.material_count }} 个材料 / 知识库 v{{ c.knowledge_version || 0 }}）
              </option>
            </select>
          </div>

          <div v-if="matCatId">
            <!-- 上传 -->
            <div class="card" style="background: var(--bg); margin-bottom: 16px">
              <div class="field">
                <label>上传资料文件</label>
                <input type="file" class="input" @change="onFileChange" accept=".txt,.md,.json,.docx,.pptx,.pdf,.xlsx" />
                <div class="muted" style="font-size:12px;margin-top:4px">支持 TXT / MD / DOCX / PPTX / PDF / XLSX</div>
              </div>
              <div class="row">
                <div class="field" style="flex:1">
                  <label>资料类型</label>
                  <select class="input" v-model="uploadSourceType">
                    <option value="sales">销售案例</option>
                    <option value="product">产品知识</option>
                    <option value="sop">SOP流程</option>
                    <option value="training">培训教材</option>
                    <option value="faq">FAQ</option>
                  </select>
                </div>
                <div class="field" style="flex:1" v-if="uploadSourceType === 'sales'">
                  <label>案例质量</label>
                  <select class="input" v-model="uploadQuality">
                    <option value="normal">普通</option>
                    <option value="excellent">优秀成交</option>
                    <option value="failed">失败丢单</option>
                  </select>
                </div>
              </div>
              <div class="row">
                <button class="btn" :disabled="!selectedFile || uploading" @click="onUpload">
                  {{ uploading ? '上传解析中...' : '上传资料' }}
                </button>
                <button class="btn ghost" :disabled="extracting" @click="onExtract">
                  {{ extracting ? 'AI 提取中（请等待）...' : '重新提取知识库' }}
                </button>
              </div>
              <div v-if="extractMsg" class="muted" style="margin-top:8px">{{ extractMsg }}</div>
            </div>

            <!-- 材料列表 -->
            <div class="page-sub" style="margin-top:8px">已上传材料</div>
            <table v-if="materials.length">
              <thead>
                <tr><th>文件名</th><th>格式</th><th>资料类型</th><th>案例</th><th>大小</th><th>上传时间</th><th>操作</th></tr>
              </thead>
              <tbody>
                <tr v-for="m in materials" :key="m.id">
                  <td>{{ m.filename }}</td>
                  <td><span class="tag gray">{{ m.file_type }}</span></td>
                  <td><span class="tag" :class="sourceTypeTagClass(m.source_type)">{{ sourceTypeLabel(m.source_type) }}</span></td>
                  <td><span v-if="m.source_type === 'sales'" class="tag" :class="qualityTagClass(m.quality)">{{ qualityLabel(m.quality) }}</span><span v-else class="muted">-</span></td>
                  <td class="muted">{{ humanSize(m.file_size) }}</td>
                  <td>{{ fmt(m.created_at) }}</td>
                  <td>
                    <button class="btn sm" style="margin-right:6px" @click="onEditMaterial(m)">编辑</button>
                    <button class="btn danger sm" @click="onDeleteMaterial(m.id)">删除</button>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-else class="empty">该分类暂无材料，请上传</div>

            <!-- 知识库展示 -->
            <div v-if="knowledge" style="margin-top: 20px">
              <div class="page-sub" style="margin-top:8px">
                结构化知识库
                <span class="tag ok">v{{ knowledge.version }}</span>
              </div>
              <div class="card" style="background: var(--bg)">
                <div v-if="knowledge.content.product_summary" class="field">
                  <label>产品概述</label>
                  <div>{{ knowledge.content.product_summary }}</div>
                </div>
                <div v-if="knowledge.content.required_questions?.length" class="field">
                  <label>客服必问项（评分核心依据）</label>
                  <div>
                    <span v-for="q in knowledge.content.required_questions" :key="q" class="tag" style="margin:0 6px 6px 0">{{ q }}</span>
                  </div>
                </div>
                <div v-if="knowledge.content.common_objections?.length" class="field">
                  <label>客户常见异议</label>
                  <div>
                    <span v-for="o in knowledge.content.common_objections" :key="o" class="tag warn" style="margin:0 6px 6px 0">{{ o }}</span>
                  </div>
                </div>
                <div v-if="knowledge.content.recommended_responses?.length" class="field">
                  <label>推荐应答</label>
                  <div v-for="(r, i) in knowledge.content.recommended_responses" :key="i" style="margin-bottom:6px">
                    <strong>{{ r.scenario }}：</strong>{{ r.guideline }}
                  </div>
                </div>
                <div v-if="knowledge.content.product_specs && Object.keys(knowledge.content.product_specs).length" class="field">
                  <label>产品规格</label>
                  <table>
                    <tbody>
                      <tr v-for="(v, k) in knowledge.content.product_specs" :key="k">
                        <td style="width:120px"><strong>{{ k }}</strong></td>
                        <td>{{ v }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-if="knowledge.content.key_knowledge?.length" class="field">
                  <label>核心知识点</label>
                  <ul>
                    <li v-for="k in knowledge.content.key_knowledge" :key="k">{{ k }}</li>
                  </ul>
                </div>
                <div v-if="knowledge.content.success_patterns?.length" class="field">
                  <label>成功模式（优秀案例提炼）</label>
                  <div v-for="(s, i) in knowledge.content.success_patterns" :key="i" class="card" style="background:var(--panel);margin-bottom:8px;padding:10px;border-left:3px solid var(--success)">
                    <div><strong>{{ s.scenario }}</strong></div>
                    <div style="font-size:13px;margin-top:4px">技巧：{{ s.technique }}</div>
                    <div v-if="s.example" style="font-size:13px;color:var(--text-soft);margin-top:2px">示例：{{ s.example }}</div>
                  </div>
                </div>
                <div v-if="knowledge.content.failure_patterns?.length" class="field">
                  <label>失败模式（丢单案例预警）</label>
                  <div v-for="(f, i) in knowledge.content.failure_patterns" :key="i" class="card" style="background:var(--panel);margin-bottom:8px;padding:10px;border-left:3px solid var(--danger)">
                    <div><strong>{{ f.scenario }}</strong></div>
                    <div style="font-size:13px;margin-top:4px;color:var(--danger)">失误：{{ f.mistake }}</div>
                    <div v-if="f.consequence" style="font-size:13px;color:var(--text-soft);margin-top:2px">后果：{{ f.consequence }}</div>
                  </div>
                </div>
                <div v-if="knowledge.content._note" class="muted" style="margin-top:8px">
                  ⚠ {{ knowledge.content._note }}
                </div>
              </div>
            </div>
            <div v-else class="empty" style="margin-top:16px">该分类尚未提取知识库，点击上方「重新提取知识库」</div>

            <!-- 编辑材料弹窗 -->
            <div v-if="editingMaterial" class="modal-overlay" @click.self="onCancelEdit">
              <div class="modal-card">
                <div class="modal-header">
                  <strong>编辑材料</strong>
                  <span class="muted" style="margin-left:12px">{{ editingMaterial.filename }}</span>
                </div>
                <div class="field">
                  <label>文件名</label>
                  <input class="input" v-model="editFilename" />
                </div>
                <div class="field">
                  <label>资料类型</label>
                  <select class="input" v-model="editSourceType">
                    <option value="sales">销售案例</option>
                    <option value="product">产品知识</option>
                    <option value="sop">SOP流程</option>
                    <option value="training">培训教材</option>
                    <option value="faq">FAQ</option>
                  </select>
                </div>
                <div v-if="editSourceType === 'sales'" class="field">
                  <label>案例质量</label>
                  <select class="input" v-model="editQuality">
                    <option value="normal">普通</option>
                    <option value="excellent">优秀成交</option>
                    <option value="failed">失败丢单</option>
                  </select>
                </div>
                <div class="field">
                  <label>内容（纯文本）</label>
                  <textarea
                    class="input mono"
                    v-model="editContent"
                    rows="16"
                    style="font-size:13px;font-family:Consolas,monospace"
                  ></textarea>
                </div>
                <div class="row" style="justify-content:flex-end;margin-top:12px">
                  <button class="btn ghost" @click="onCancelEdit">取消</button>
                  <button class="btn" :disabled="editSaving" @click="onSaveEdit">
                    {{ editSaving ? '保存中...' : '保存' }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 训练成绩 -->
        <div v-if="tab === 'scores'">
          <div class="page-title">训练成绩查询</div>
          <div class="page-sub">查看所有客服的训练记录与 AI 评分，支持按客服/分类筛选</div>

          <!-- 筛选 -->
          <div class="row" style="margin-bottom: 16px">
            <select class="input" v-model="scoreFilter.user_id">
              <option :value="null">全部客服</option>
              <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.username }}</option>
            </select>
            <select class="input" v-model="scoreFilter.category_id">
              <option :value="null">全部分类</option>
              <option v-for="c in cats" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
            <button class="btn" style="flex: 0 0 auto" @click="loadScoreList">查询</button>
          </div>

          <!-- 列表 -->
          <table v-if="scoreList.length">
            <thead>
              <tr>
                <th>ID</th><th>客服</th><th>分类</th><th>状态</th>
                <th>消息数</th><th>分数</th><th>总评</th><th>时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in scoreList" :key="s.id">
                <td>{{ s.id }}</td>
                <td>{{ s.username }}</td>
                <td>{{ s.category_name }}</td>
                <td>
                  <span v-if="s.status === 'completed'" class="tag ok">已完成</span>
                  <span v-else class="tag warn">进行中</span>
                </td>
                <td>{{ s.message_count }}</td>
                <td>
                  <strong v-if="s.score_total !== null" :class="scoreClass(s.score_total)">{{ s.score_total.toFixed(1) }}</strong>
                  <span v-else class="muted">-</span>
                </td>
                <td class="muted" style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ s.score_summary || '-' }}</td>
                <td>{{ fmt(s.started_at) }}</td>
                <td><button class="btn sm" @click="onViewScore(s.id)">查看</button></td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty">暂无训练记录</div>

          <!-- 详情弹窗 -->
          <div v-if="scoreDetail" class="modal-overlay" @click.self="scoreDetail = null">
            <div class="modal-card" style="max-width:760px">
              <div class="modal-header">
                <strong>训练详情 #{{ scoreDetail.id }}</strong>
                <span class="muted" style="margin-left:12px">
                  {{ scoreDetail.username }} · {{ scoreDetail.category_name }} · {{ fmt(scoreDetail.started_at) }}
                </span>
              </div>

              <!-- 评分卡片 -->
              <div v-if="scoreDetail.score" class="card" style="background:var(--bg);margin-bottom:12px">
                <div class="row" style="align-items:center;margin-bottom:8px">
                  <div style="font-size:28px;font-weight:bold" :class="scoreClass(scoreDetail.score.total_score)">
                    {{ scoreDetail.score.total_score.toFixed(1) }}
                  </div>
                  <div class="muted" style="margin-left:8px">/ 100</div>
                </div>

                <!-- 四维评分 -->
                <div v-if="scoreDetail.score.dimension_scores && Object.keys(scoreDetail.score.dimension_scores).length" style="margin-bottom:12px">
                  <div v-for="dim in dimConfig" :key="dim.key" style="margin-bottom:6px">
                    <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:2px">
                      <span>{{ dim.label }}</span>
                      <span :class="adminDimClass(dim.key)">{{ scoreDetail.score.dimension_scores[dim.key] || 0 }}/{{ dim.max }}</span>
                    </div>
                    <div style="height:6px;background:var(--border);border-radius:3px;overflow:hidden">
                      <div :style="{ width: adminDimPercent(dim.key) + '%', height: '100%', background: adminDimColor(dim.key), borderRadius: '3px' }"></div>
                    </div>
                  </div>
                </div>

                <div class="field">
                  <label>总评</label>
                  <div>{{ scoreDetail.score.summary }}</div>
                </div>
                <div v-if="scoreDetail.score.advantages?.length" class="field">
                  <label>优点</label>
                  <ul>
                    <li v-for="(t, i) in scoreDetail.score.advantages" :key="i" style="color:var(--success)">{{ t }}</li>
                  </ul>
                </div>
                <div v-if="scoreDetail.score.mistakes?.length" class="field">
                  <label>不足</label>
                  <ul>
                    <li v-for="(t, i) in scoreDetail.score.mistakes" :key="i" style="color:var(--danger)">{{ t }}</li>
                  </ul>
                </div>
                <div v-if="scoreDetail.score.suggestions?.length" class="field">
                  <label>建议</label>
                  <ul>
                    <li v-for="(t, i) in scoreDetail.score.suggestions" :key="i">{{ t }}</li>
                  </ul>
                </div>
              </div>
              <div v-else class="empty" style="margin-bottom:12px">该训练尚未评分</div>

              <!-- 对话记录 -->
              <div class="page-sub" style="margin-bottom:8px">对话记录（{{ scoreDetail.messages.length }} 条）</div>
              <div style="max-height:360px;overflow-y:auto">
                <div
                  v-for="m in scoreDetail.messages"
                  :key="m.id"
                  style="margin-bottom:8px;padding:8px 12px;border-radius:6px"
                  :style="m.role === 'agent' ? 'background:var(--bg)' : 'background:var(--bg-soft, #f0f7ff);border-left:3px solid var(--primary)'"
                >
                  <div class="muted" style="font-size:12px;margin-bottom:2px">
                    {{ m.role === 'agent' ? '客服' : 'AI客户' }} · {{ fmt(m.created_at) }}
                  </div>
                  <div>{{ m.content }}</div>
                </div>
              </div>

              <div class="row" style="justify-content:flex-end;margin-top:12px">
                <button class="btn ghost" @click="scoreDetail = null">关闭</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 成绩趋势 -->
        <div v-if="tab === 'trend'">
          <div class="page-title">训练成绩成长趋势</div>
          <div class="page-sub">按「客服 × 分类」聚合每次训练评分，直观看培训是否有效——分数持续上升说明成长明显。</div>

          <!-- 筛选 -->
          <div class="row" style="margin-bottom: 16px">
            <select class="input" v-model="trendFilter.user_id">
              <option :value="null">全部客服</option>
              <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.username }}</option>
            </select>
            <select class="input" v-model="trendFilter.category_id">
              <option :value="null">全部分类</option>
              <option v-for="c in cats" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
            <select class="input" v-model="trendFilter.days">
              <option :value="30">最近 30 天</option>
              <option :value="90">最近 90 天</option>
              <option :value="180">最近 180 天</option>
              <option :value="365">最近 1 年</option>
            </select>
            <button class="btn" style="flex: 0 0 auto" @click="loadTrends">查询</button>
          </div>

          <!-- 成长趋势汇总卡片 -->
          <div v-if="trendSeries.length" class="trend-cards">
            <div v-for="s in trendSeries" :key="s.user_id + '-' + s.category_id" class="trend-card">
              <div class="trend-card-head">{{ s.username }} · {{ s.category_name }}</div>
              <div class="trend-card-body">
                <div class="trend-score" :class="scoreClass(s.latest_score)">
                  {{ s.latest_score != null ? s.latest_score.toFixed(1) : '-' }}
                </div>
                <div class="trend-delta" :class="trendDeltaClass(s.trend)">
                  <template v-if="s.trend === 'up'">↑ 进步 {{ s.delta.toFixed(1) }}</template>
                  <template v-else-if="s.trend === 'down'">↓ 退步 {{ Math.abs(s.delta).toFixed(1) }}</template>
                  <template v-else>→ 持平</template>
                </div>
              </div>
              <div class="trend-card-foot">共 {{ s.count }} 次训练</div>
            </div>
          </div>

          <!-- 折线图 -->
          <div v-if="trendSeries.length" ref="trendChart" class="trend-chart"></div>
          <div v-else class="empty">该筛选条件下暂无已评分的训练记录</div>
        </div>

        <!-- 导入语料 -->
        <div v-if="tab === 'import'" class="import-panel">
          <div class="page-title">导入聊天语料</div>
          <div class="page-sub">粘贴原始聊天记录，系统自动清洗 → 角色识别 → 入库 → LLM 提取</div>

          <div class="row" style="margin-bottom: 12px">
            <select class="input" v-model="importForm.category_id">
              <option :value="0" disabled>选择品类</option>
              <option v-for="c in cats" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
            <select class="input" v-model="importForm.quality">
              <option value="excellent">成交案例</option>
              <option value="failed">未成交案例</option>
              <option value="normal">普通案例</option>
            </select>
          </div>

          <textarea
            class="input" style="height:260px;font-family:monospace;font-size:13px"
            v-model="importForm.raw_text"
            placeholder="粘贴原始聊天记录..."
          ></textarea>

          <div style="margin-top:12px">
            <button class="btn" @click="onImportChat" :disabled="importing">
              {{ importing ? '导入中...' : '导入并提取知识' }}
            </button>
            <button class="btn ghost" @click="importForm.raw_text = ''; importResult = null" style="margin-left:8px">
              清空
            </button>
          </div>

          <div v-if="importResult" class="import-result">
            <div class="result-header">
              导入完成 —
              <span :class="importResult.used_llm ? 'green' : 'orange'">
                {{ importResult.used_llm ? 'LLM 提取' : '规则模式' }}
              </span>
              · knowledge v{{ importResult.knowledge_version }}
            </div>
            <div class="result-stats">
              <span class="stat">成功模式 {{ importResult.success_count }} 条</span>
              <span class="stat">失败模式 {{ importResult.failure_count }} 条</span>
            </div>
            <ul v-if="importResult.extracted_patterns.length" class="pattern-list">
              <li v-for="p in importResult.extracted_patterns" :key="p">{{ p }}</li>
            </ul>
          </div>

          <div v-if="importError" class="msg danger" style="margin-top:12px">{{ importError }}</div>
        </div>

        <!-- 训练管理（批次判定） -->
        <div v-if="tab === 'batches'">
          <div class="page-title">训练管理（主管判定）</div>
          <div class="page-sub">
            客服每练完一批（20 题），主管逐题判定「合适/不合适」。
            不合适 → 进该客服错题本，间隔混入后续批次；合适 → 解错题。
            全部判定完，客服才能开下一批。
          </div>

          <div class="row" style="margin-bottom: 16px">
            <select class="input" v-model="batchFilter.user_id">
              <option :value="null">全部客服</option>
              <option v-for="a in agents" :key="a.id" :value="a.id">{{ a.username }}</option>
            </select>
            <select class="input" v-model="batchFilter.status">
              <option :value="null">全部状态</option>
              <option value="in_progress">训练中</option>
              <option value="awaiting_review">待判定</option>
              <option value="reviewed">已判定</option>
            </select>
            <button class="btn" style="flex: 0 0 auto" @click="loadBatches">查询</button>
          </div>

          <table v-if="batchList.length">
            <thead>
              <tr>
                <th>ID</th><th>客服</th><th>分类</th><th>状态</th>
                <th>题数</th><th>已判定</th><th>开始时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="b in batchList" :key="b.id">
                <td>{{ b.id }}</td>
                <td>{{ b.username }}</td>
                <td>{{ b.category_name }}</td>
                <td>
                  <span class="tag" :class="batchStatusTagClass(b.status)">{{ batchStatusLabel(b.status) }}</span>
                </td>
                <td>{{ b.question_count }}</td>
                <td>{{ b.reviewed_count }}/{{ b.question_count }}</td>
                <td>{{ fmt(b.created_at) }}</td>
                <td>
                  <button class="btn sm" @click="onViewBatch(b.id)">
                    {{ b.status === 'awaiting_review' ? '去判定' : '查看' }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty">暂无训练批次</div>

          <!-- 批次判定弹窗 -->
          <div v-if="batchDetail" class="modal-overlay" @click.self="batchDetail = null">
            <div class="modal-card" style="max-width:880px">
              <div class="modal-header">
                <strong>批次 #{{ batchDetail.id }} · {{ batchDetail.username }} · {{ batchDetail.category_name }}</strong>
                <span class="tag" :class="batchStatusTagClass(batchDetail.status)" style="margin-left:12px">
                  {{ batchStatusLabel(batchDetail.status) }}
                </span>
              </div>
              <div style="max-height:58vh;overflow-y:auto">
                <div
                  v-for="it in batchDetail.items"
                  :key="it.id"
                  class="card"
                  style="background:var(--bg);padding:12px;margin-bottom:10px"
                  :style="it.review_status === 'approved' ? 'border-left:3px solid var(--success)' : (it.review_status === 'rejected' ? 'border-left:3px solid var(--danger)' : '')"
                >
                  <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                    <span class="tag gray">第 {{ it.seq }} 题</span>
                    <strong>{{ it.question_title }}</strong>
                    <span v-if="it.is_mistake" class="tag warn">错题</span>
                    <span v-if="it.session_status === 'completed'" class="tag ok">已练</span>
                    <span v-else class="tag gray">未练</span>
                    <span v-if="it.score_total !== null" :class="scoreClass(it.score_total)" style="font-weight:600">
                      {{ it.score_total.toFixed(1) }} 分
                    </span>
                  </div>

                  <!-- 已判定 -->
                  <div v-if="it.review_status !== 'pending'" style="margin-top:8px">
                    <span class="tag" :class="it.review_status === 'approved' ? 'ok' : 'danger'">
                      {{ it.review_status === 'approved' ? '✅ 合适' : '❌ 不合适' }}
                    </span>
                  </div>
                  <!-- 待判定：本地暂选 + 提交 -->
                  <div v-else style="margin-top:8px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                    <template v-if="reviewMap[it.question_id] === undefined">
                      <button class="btn sm" @click="onJudge(it.question_id, true)">合适</button>
                      <button class="btn sm danger" @click="onJudge(it.question_id, false)">不合适</button>
                    </template>
                    <template v-else>
                      <span class="tag" :class="reviewMap[it.question_id] ? 'ok' : 'danger'">
                        已选：{{ reviewMap[it.question_id] ? '合适' : '不合适' }}
                      </span>
                      <button class="btn ghost sm" @click="onUnjudge(it.question_id)">取消</button>
                    </template>
                    <button v-if="it.session_id" class="btn ghost sm" @click="onViewScore(it.session_id)">看对话</button>
                  </div>
                </div>
              </div>
              <div class="row" style="justify-content:flex-end;margin-top:12px">
                <span v-if="batchReviewCount" class="muted" style="margin-right:12px">已选 {{ batchReviewCount }} 题待提交</span>
                <button class="btn" :disabled="!batchReviewCount || reviewing" @click="onSubmitReview">
                  {{ reviewing ? '提交中...' : `提交判定（${batchReviewCount} 题）` }}
                </button>
                <button class="btn ghost" @click="batchDetail = null">关闭</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 题库管理 -->
        <div v-if="tab === 'questions'">
          <div class="page-title">题库管理</div>
          <div class="page-sub">
            题目 = 客户剧本。已上传的销售聊天记录（导入语料）可一键转为题目；
            AI 客户训练时按题目剧本衍生扮演，错题本基于题目维度工作。
          </div>

          <div class="row" style="margin-bottom: 16px">
            <select class="input" v-model="qCatId" @change="loadQuestions">
              <option v-for="c in cats" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
            <button class="btn" style="flex: 0 0 auto" :disabled="syncingQ" @click="onSyncQuestions">
              {{ syncingQ ? '同步中...' : '同步题目（从聊天记录）' }}
            </button>
            <button class="btn ghost" style="flex: 0 0 auto" @click="loadQuestions">刷新</button>
          </div>
          <div v-if="syncMsg" class="muted" style="margin-bottom:10px">{{ syncMsg }}</div>

          <table v-if="questions.length">
            <thead>
              <tr><th>ID</th><th>题目</th><th>客户场景</th><th>知识点</th><th>难度</th><th>来源</th><th>创建时间</th></tr>
            </thead>
            <tbody>
              <tr v-for="q in questions" :key="q.id">
                <td>{{ q.id }}</td>
                <td><strong>{{ q.title }}</strong></td>
                <td class="muted" style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ q.scenario || '-' }}</td>
                <td>
                  <select class="input" style="min-width:120px" :value="q.skill_id || ''" @change="onBindSkill(q, $event.target.value)">
                    <option value="">未归类</option>
                    <option v-for="s in skills" :key="s.id" :value="s.id">{{ s.name }}</option>
                  </select>
                </td>
                <td>
                  <select class="input" style="min-width:70px" :value="q.difficulty || 'medium'" @change="onBindDiff(q, $event.target.value)">
                    <option value="easy">易</option>
                    <option value="medium">中</option>
                    <option value="hard">难</option>
                  </select>
                </td>
                <td>
                  <span class="tag" :class="q.source_type === 'ai' ? 'warn' : 'gray'">
                    {{ q.source_type === 'ai' ? 'AI 衍生' : '上传语料' }}
                  </span>
                </td>
                <td>{{ fmt(q.created_at) }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty">该品类暂无题目，请先在「导入语料」粘贴聊天记录，再点「同步题目」</div>
        </div>

        <!-- 掌握度看板 + 知识点管理（v0.8） -->
        <div v-if="tab === 'mastery'">
          <div class="row" style="margin-bottom:6px">
            <div class="field" style="flex:1;margin-bottom:0">
              <label>选择训练分类</label>
              <select class="input" v-model="masteryCatId" @change="loadMasteryOverview">
                <option v-for="c in cats" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
            </div>
            <button class="btn ghost" @click="loadMasteryOverview" style="align-self:flex-end">刷新</button>
          </div>

          <!-- 薄弱知识点排行 -->
          <div v-if="overview && overview.weak_ranking.length" style="margin-top:16px">
            <div class="section-title">薄弱知识点排行（平均掌握度从低到高）</div>
            <table>
              <thead><tr><th>知识点</th><th>平均掌握度</th><th>薄弱人数</th></tr></thead>
              <tbody>
                <tr v-for="w in overview.weak_ranking" :key="w.skill_id">
                  <td><strong>{{ w.skill_name }}</strong></td>
                  <td><span class="tag" :class="w.avg_mastery < 50 ? 'warn' : 'ok'">{{ w.avg_mastery }}%</span></td>
                  <td>{{ w.weak_count }} 人</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 团队掌握度矩阵 -->
          <div v-if="overview && overview.rows.length" style="margin-top:16px">
            <div class="section-title">团队掌握度矩阵（客服 × 知识点）</div>
            <div style="overflow-x:auto">
              <table>
                <thead>
                  <tr>
                    <th>客服</th>
                    <th v-for="s in overview.skills" :key="s.id" :title="s.name">{{ s.name }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="agent in overview.agents" :key="agent.id">
                    <td><strong>{{ agent.name }}</strong></td>
                    <td v-for="s in overview.skills" :key="s.id">
                      <span class="tag" :class="cellClass(getMastery(agent.id, s.id))">{{ getMastery(agent.id, s.id) }}%</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- 知识点管理 -->
          <div style="margin-top:24px">
            <div class="section-title">知识点管理（AI 提炼 + 手工维护）</div>
            <div class="row" style="margin-bottom:10px">
              <input class="input" v-model="skillForm.name" placeholder="知识点名，如：报价计算" style="flex:1" />
              <input class="input" v-model="skillForm.description" placeholder="考察内容说明（可选）" style="flex:2" />
              <button class="btn" :disabled="!skillForm.name.trim()" @click="onCreateSkill">添加</button>
            </div>
            <table v-if="overview && overview.skills.length">
              <thead><tr><th>ID</th><th>名称</th><th>描述</th><th>来源</th><th>绑定题数</th><th>操作</th></tr></thead>
              <tbody>
                <tr v-for="s in overview.skills" :key="s.id">
                  <td>{{ s.id }}</td>
                  <td><strong>{{ s.name }}</strong></td>
                  <td class="muted">{{ s.description || '-' }}</td>
                  <td><span class="tag" :class="s.source === 'ai' ? 'gray' : 'ok'">{{ s.source === 'ai' ? 'AI 提炼' : '手工' }}</span></td>
                  <td>{{ s.question_count }}</td>
                  <td>
                    <button class="btn ghost sm" @click="onEditSkill(s)">改</button>
                    <button class="btn ghost sm" @click="onDeleteSkill(s)">删</button>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-else class="empty">该品类还没有知识点，可在上方手动添加，或提取知识库后自动生成。</div>
          </div>
        </div>

        <!-- 快捷短语管理（v0.9） -->
        <div v-if="tab === 'quick'">
          <div class="section-title">快捷回复短语（客服训练时点选，千牛式分组）</div>
          <div class="row" style="margin-bottom:10px">
            <input class="input" v-model="quickForm.group_name" placeholder="分组（如：常用回复/催付/议价）" style="flex:0 0 180px" />
            <input class="input" v-model="quickForm.content" placeholder="输入短语内容，如：好的，请问您需要什么规格？" style="flex:1" @keyup.enter="onCreateQuick" />
            <button class="btn" :disabled="!quickForm.content.trim()" @click="onCreateQuick">添加</button>
          </div>
          <div v-if="quickList.length" class="muted" style="margin-bottom:8px">
            共 {{ quickList.length }} 条，启用 {{ quickList.filter(q => q.is_active).length }} 条
          </div>
          <table v-if="quickList.length">
            <thead>
              <tr><th>分组</th><th>短语内容</th><th>状态</th><th>创建时间</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="(q, i) in quickList" :key="q.id">
                <td><span class="tag gray">{{ q.group_name || '常用回复' }}</span></td>
                <td style="max-width:420px">{{ q.content }}</td>
                <td>
                  <button class="btn ghost sm" @click="onToggleQuick(q)">
                    <span class="tag" :class="q.is_active ? 'ok' : 'gray'">{{ q.is_active ? '启用' : '停用' }}</span>
                  </button>
                </td>
                <td class="muted">{{ fmt(q.created_at) }}</td>
                <td>
                  <button class="btn ghost sm" @click="onEditQuick(q)">改</button>
                  <button class="btn ghost sm" @click="onDeleteQuick(q)">删</button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty">还没有快捷短语，在上方添加第一条。</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, nextTick, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import {
  listAgents, createAgent, deleteAgent,
  listCategoriesAdmin, createCategory, deleteCategory,
  listMaterials, uploadMaterial, deleteMaterial, getMaterial, updateMaterial,
  getKnowledge, extractKnowledge,
  listAdminSessions, getAdminSession, getScoreTrends,
  importChat,
  listAdminBatches, getAdminBatch, reviewBatch,
  listQuestions, syncQuestions,
  listSkills, createSkill, updateSkill, deleteSkill, masteryOverview,
  listQuickReplies, createQuickReply, updateQuickReply, deleteQuickReply,
} from '../api.js'

const router = useRouter()
const username = localStorage.getItem('username') || '管理员'
const tab = ref('agents')

const agents = ref([])
const agentForm = reactive({ username: '', password: '' })

const cats = ref([])
const catForm = reactive({ name: '', description: '' })

const matCatId = ref(null)
const materials = ref([])
const knowledge = ref(null)
const selectedFile = ref(null)
const uploading = ref(false)
const uploadQuality = ref('normal')
const uploadSourceType = ref('sales')
const extracting = ref(false)
const extractMsg = ref('')

// 编辑材料
const editingMaterial = ref(null)
const editContent = ref('')
const editFilename = ref('')
const editQuality = ref('normal')
const editSourceType = ref('sales')
const editSaving = ref(false)

// 训练成绩
const scoreList = ref([])
const scoreFilter = reactive({ user_id: null, category_id: null })
const scoreDetail = ref(null)

// 成绩趋势
const trendSeries = ref([])
const trendFilter = reactive({ user_id: null, category_id: null, days: 90 })
const trendChart = ref(null)
let trendChartInstance = null

const llmHint = computed(() => {
  // 从根接口读 llm_enabled（简化：默认提示）
  return '配置 LLM_API_KEY 后提取为真实 AI 总结，否则为规则模式。'
})

function fmt(d) {
  if (!d) return '-'
  return new Date(d).toLocaleString('zh-CN')
}
function humanSize(b) {
  if (!b) return '-'
  if (b < 1024) return b + ' B'
  if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB'
  return (b / 1024 / 1024).toFixed(2) + ' MB'
}
function qualityLabel(q) {
  const map = { excellent: '优秀', normal: '普通', failed: '失败' }
  return map[q] || '普通'
}
function qualityTagClass(q) {
  if (q === 'excellent') return 'ok'
  if (q === 'failed') return 'warn'
  return 'gray'
}
function sourceTypeLabel(s) {
  const map = { product: '产品知识', sales: '销售案例', sop: 'SOP', training: '培训教材', faq: 'FAQ' }
  return map[s] || '销售案例'
}
function sourceTypeTagClass(s) {
  if (s === 'product') return 'ok'
  if (s === 'sop') return 'warn'
  if (s === 'faq') return 'gray'
  return ''
}
function logout() {
  localStorage.clear()
  router.push('/login')
}

async function loadAgents() {
  const { data } = await listAgents()
  agents.value = data
}
async function onCreateAgent() {
  if (!agentForm.username || !agentForm.password) return alert('请填写用户名和密码')
  try {
    await createAgent({ ...agentForm })
    agentForm.username = ''
    agentForm.password = ''
    await loadAgents()
  } catch (e) {
    alert(e.response?.data?.detail || '新增失败')
  }
}
async function onDeleteAgent(id) {
  if (!confirm('确认删除该客服账号？')) return
  await deleteAgent(id)
  await loadAgents()
}

async function loadCats() {
  const { data } = await listCategoriesAdmin()
  cats.value = data
  if (!matCatId.value && data.length) {
    matCatId.value = data[0].id
    await onCatChange()
  }
}
async function onCreateCat() {
  if (!catForm.name) return alert('请填写分类名称')
  try {
    await createCategory({ ...catForm })
    catForm.name = ''
    catForm.description = ''
    await loadCats()
  } catch (e) {
    alert(e.response?.data?.detail || '新增失败')
  }
}
async function onDeleteCat(id) {
  if (!confirm('删除分类将同时删除其所有材料与知识库，确认？')) return
  await deleteCategory(id)
  await loadCats()
}

function onFileChange(e) {
  selectedFile.value = e.target.files[0] || null
}
async function onUpload() {
  if (!selectedFile.value || !matCatId.value) return
  uploading.value = true
  try {
    await uploadMaterial(matCatId.value, selectedFile.value, uploadQuality.value, uploadSourceType.value)
    selectedFile.value = null
    uploadQuality.value = 'normal'
    uploadSourceType.value = 'sales'
    await loadMaterials()
    await loadCats()
  } catch (e) {
    alert(e.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}
async function loadMaterials() {
  if (!matCatId.value) return
  const { data } = await listMaterials(matCatId.value)
  materials.value = data
}
async function loadKnowledge() {
  if (!matCatId.value) return
  try {
    const { data } = await getKnowledge(matCatId.value)
    knowledge.value = data
  } catch (e) {
    if (e.response?.status === 404) knowledge.value = null
    else throw e
  }
}
async function onCatChange() {
  await Promise.all([loadMaterials(), loadKnowledge()])
}
async function onDeleteMaterial(id) {
  if (!confirm('确认删除该材料？')) return
  await deleteMaterial(id)
  await loadMaterials()
  await loadCats()
}
async function onEditMaterial(m) {
  try {
    const { data } = await getMaterial(m.id)
    editingMaterial.value = data
    editContent.value = data.content_text || ''
    editFilename.value = data.filename || ''
    editQuality.value = data.quality || 'normal'
    editSourceType.value = data.source_type || 'sales'
  } catch (e) {
    alert(e.response?.data?.detail || '加载材料失败')
  }
}
function onCancelEdit() {
  editingMaterial.value = null
  editContent.value = ''
  editFilename.value = ''
  editQuality.value = 'normal'
  editSourceType.value = 'sales'
}
async function onSaveEdit() {
  if (!editingMaterial.value) return
  editSaving.value = true
  try {
    await updateMaterial(editingMaterial.value.id, {
      filename: editFilename.value || undefined,
      content_text: editContent.value,
      quality: editQuality.value,
      source_type: editSourceType.value,
    })
    editingMaterial.value = null
    await loadMaterials()
  } catch (e) {
    alert(e.response?.data?.detail || '保存失败')
  } finally {
    editSaving.value = false
  }
}
async function onExtract() {
  if (!matCatId.value) return
  if (!confirm('将用 AI 从当前所有材料重新提取知识库（会生成新版本），确认？')) return
  extracting.value = true
  extractMsg.value = ''
  try {
    const { data } = await extractKnowledge(matCatId.value)
    extractMsg.value = data.message
    await loadKnowledge()
    await loadCats()
  } catch (e) {
    alert(e.response?.data?.detail || '提取失败')
  } finally {
    extracting.value = false
  }
}

// ---------- 训练成绩 ----------
function onTabScores() {
  tab.value = 'scores'
  loadScoreList()
}
async function loadScoreList() {
  try {
    const params = {}
    if (scoreFilter.user_id) params.user_id = scoreFilter.user_id
    if (scoreFilter.category_id) params.category_id = scoreFilter.category_id
    const { data } = await listAdminSessions(params)
    scoreList.value = data
  } catch (e) {
    alert(e.response?.data?.detail || '加载失败')
  }
}
async function onViewScore(id) {
  try {
    const { data } = await getAdminSession(id)
    scoreDetail.value = data
  } catch (e) {
    alert(e.response?.data?.detail || '加载详情失败')
  }
}
function scoreClass(score) {
  if (score >= 80) return 'ok-text'
  if (score >= 60) return 'warn-text'
  return 'danger-text'
}
function trendDeltaClass(trend) {
  if (trend === 'up') return 'ok-text'
  if (trend === 'down') return 'danger-text'
  return 'muted'
}

// ---------- 成绩趋势 ----------
function onTabTrend() {
  tab.value = 'trend'
  loadTrends()
}
async function loadTrends() {
  try {
    const params = { days: trendFilter.days }
    if (trendFilter.user_id) params.user_id = trendFilter.user_id
    if (trendFilter.category_id) params.category_id = trendFilter.category_id
    const { data } = await getScoreTrends(params)
    trendSeries.value = data.series || []
    await nextTick()
    renderTrendChart()
  } catch (e) {
    alert(e.response?.data?.detail || '加载趋势失败')
  }
}
function renderTrendChart() {
  if (!trendChart.value) return
  if (!trendChartInstance) {
    trendChartInstance = echarts.init(trendChart.value)
  }
  // 所有系列出现的日期并集（排序去重），作为 X 轴
  const dateSet = new Set()
  trendSeries.value.forEach((s) => s.points.forEach((p) => dateSet.add(p.date)))
  const dates = Array.from(dateSet).sort()

  const palette = ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#a855f7', '#06b6d4', '#ec4899', '#84cc16']
  const series = trendSeries.value.map((s, idx) => {
    const map = {}
    s.points.forEach((p) => { map[p.date] = p.total_score })
    return {
      name: `${s.username}-${s.category_name}`,
      type: 'line',
      smooth: true,
      connectNulls: true,
      symbol: 'circle',
      symbolSize: 7,
      lineStyle: { width: 2 },
      itemStyle: { color: palette[idx % palette.length] },
      data: dates.map((d) => (d in map ? map[d] : null)),
    }
  })

  trendChartInstance.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => (v == null ? '-' : v.toFixed(1) + ' 分'),
    },
    legend: {
      type: 'scroll',
      top: 0,
      textStyle: { color: '#94a3b8' },
    },
    grid: { left: 48, right: 24, top: 48, bottom: 40 },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#475569' } },
      axisLabel: { color: '#94a3b8' },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      name: '分数',
      nameTextStyle: { color: '#94a3b8' },
      axisLabel: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: 'rgba(148,163,184,0.15)' } },
    },
    series,
  }, true)
  trendChartInstance.resize()
}
function disposeTrendChart() {
  if (trendChartInstance) {
    trendChartInstance.dispose()
    trendChartInstance = null
  }
}

// 评分维度（从评分详情动态读取）
const dimConfig = computed(() => {
  const dims = scoreDetail.value?.score?.scoring_dimensions
  if (dims && Object.keys(dims).length) {
    return Object.entries(dims).map(([key, max]) => ({ key, label: key, max }))
  }
  return [
    { key: '需求确认', label: '需求确认', max: 30 },
    { key: '产品专业', label: '产品专业', max: 25 },
    { key: '报价能力', label: '报价能力', max: 25 },
    { key: '风险控制', label: '风险控制', max: 20 },
  ]
})
function adminDimPercent(key) {
  const val = scoreDetail.value?.score?.dimension_scores?.[key] || 0
  const max = dimConfig.find(d => d.key === key)?.max || 20
  return Math.min(100, (val / max) * 100)
}
function adminDimClass(key) {
  const ratio = adminDimPercent(key)
  if (ratio >= 80) return 'ok-text'
  if (ratio >= 60) return 'warn-text'
  return 'danger-text'
}
function adminDimColor(key) {
  const ratio = adminDimPercent(key)
  if (ratio >= 80) return '#22c55e'
  if (ratio >= 60) return '#f59e0b'
  return '#ef4444'
}

onMounted(async () => {
  await loadAgents()
  await loadCats()
  window.addEventListener('resize', onTrendResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onTrendResize)
  disposeTrendChart()
})
watch(tab, (v) => {
  if (v !== 'trend') disposeTrendChart()
})
function onTrendResize() {
  if (trendChartInstance) trendChartInstance.resize()
}

// ---------- 导入语料 ----------
const importForm = reactive({ category_id: 0, quality: 'excellent', raw_text: '' })
const importing = ref(false)
const importResult = ref(null)
const importError = ref('')

async function onImportChat() {
  if (!importForm.category_id) { importError.value = '请选择品类'; return }
  if (!importForm.raw_text.trim()) { importError.value = '请输入聊天记录'; return }
  importing.value = true
  importError.value = ''
  importResult.value = null
  try {
    const { data } = await importChat({
      category_id: importForm.category_id,
      quality: importForm.quality,
      raw_text: importForm.raw_text,
    })
    importResult.value = data
    // 刷新材料列表（如果在材料tab）
    if (matCatId.value === importForm.category_id) {
      await loadMaterials(importForm.category_id)
    }
  } catch (e) {
    importError.value = e.response?.data?.detail || e.message || '导入失败'
  } finally {
    importing.value = false
  }
}

// ---------- 训练管理（批次判定，v0.7） ----------
const batchList = ref([])
const batchFilter = reactive({ user_id: null, status: null })
const batchDetail = ref(null)
const reviewMap = reactive({}) // question_id -> passed
const reviewing = ref(false)

function batchStatusLabel(s) {
  return { in_progress: '训练中', awaiting_review: '待判定', reviewed: '已判定' }[s] || s
}
function batchStatusTagClass(s) {
  if (s === 'awaiting_review') return 'warn'
  if (s === 'reviewed') return 'ok'
  return 'gray'
}
function onTabBatches() {
  tab.value = 'batches'
  loadBatches()
}
async function loadBatches() {
  try {
    const params = {}
    if (batchFilter.user_id) params.user_id = batchFilter.user_id
    if (batchFilter.status) params.status = batchFilter.status
    const { data } = await listAdminBatches(params)
    batchList.value = data
  } catch (e) {
    alert(e.response?.data?.detail || '加载批次失败')
  }
}
async function onViewBatch(id) {
  try {
    const { data } = await getAdminBatch(id)
    batchDetail.value = data
    Object.keys(reviewMap).forEach((k) => delete reviewMap[k])
  } catch (e) {
    alert(e.response?.data?.detail || '加载批次详情失败')
  }
}
function onJudge(questionId, passed) {
  reviewMap[questionId] = passed
}
function onUnjudge(questionId) {
  delete reviewMap[questionId]
}
const batchReviewCount = computed(() => Object.keys(reviewMap).length)
async function onSubmitReview() {
  const items = Object.entries(reviewMap).map(([qid, passed]) => ({
    question_id: Number(qid),
    passed,
  }))
  if (!items.length) return
  reviewing.value = true
  try {
    const { data } = await reviewBatch(batchDetail.value.id, items)
    batchDetail.value = data.batch
    Object.keys(reviewMap).forEach((k) => delete reviewMap[k])
    await loadBatches()
    alert(`已判定 ${items.length} 题` + (data.mistakes_updated ? `，其中 ${data.mistakes_updated} 题进入错题本` : ''))
  } catch (e) {
    alert(e.response?.data?.detail || '提交判定失败')
  } finally {
    reviewing.value = false
  }
}

// ---------- 掌握度看板 + 知识点管理（v0.8） ----------
const masteryCatId = ref(null)
const overview = ref(null)
const skillForm = reactive({ name: '', description: '' })

function onTabMastery() {
  tab.value = 'mastery'
  if (!masteryCatId.value && matCatId.value) masteryCatId.value = matCatId.value
  loadMasteryOverview()
}
async function loadMasteryOverview() {
  if (!masteryCatId.value) return
  try {
    const { data } = await masteryOverview(masteryCatId.value)
    overview.value = data
  } catch (e) {
    alert(e.response?.data?.detail || '加载掌握度失败')
  }
}
function getMastery(agentId, skillId) {
  const r = (overview.value?.rows || []).find(
    (x) => x.user_id === agentId && x.skill_id === skillId
  )
  return r ? r.mastery : 0
}
function cellClass(v) {
  if (v >= 80) return 'ok'
  if (v >= 50) return ''
  return 'warn'
}
async function onCreateSkill() {
  if (!masteryCatId.value) return alert('请先选择分类')
  try {
    await createSkill(masteryCatId.value, { ...skillForm })
    skillForm.name = ''
    skillForm.description = ''
    await loadMasteryOverview()
  } catch (e) {
    alert(e.response?.data?.detail || '创建知识点失败')
  }
}
function onEditSkill(s) {
  const name = prompt('知识点名', s.name)
  if (name === null) return
  updateSkill(s.id, { name: name.trim() || undefined })
    .then(loadMasteryOverview)
    .catch((e) => alert(e.response?.data?.detail || '更新失败'))
}
async function onDeleteSkill(s) {
  if (!confirm(`删除知识点「${s.name}」？关联题目的知识点标记将被清空。`)) return
  try {
    await deleteSkill(s.id)
    await loadMasteryOverview()
  } catch (e) {
    alert(e.response?.data?.detail || '删除失败')
  }
}

// ---------- 快捷短语管理（v0.9） ----------
const quickList = ref([])
const quickForm = reactive({ content: '', group_name: '常用回复' })

function onTabQuick() {
  tab.value = 'quick'
  loadQuickReplies()
}
async function loadQuickReplies() {
  try {
    const { data } = await listQuickReplies()
    quickList.value = data
  } catch (e) {
    alert(e.response?.data?.detail || '加载快捷短语失败')
  }
}
async function onCreateQuick() {
  const content = quickForm.content.trim()
  if (!content) return
  try {
    await createQuickReply({ content, group_name: quickForm.group_name.trim() || '常用回复' })
    quickForm.content = ''
    await loadQuickReplies()
  } catch (e) {
    alert(e.response?.data?.detail || '添加失败')
  }
}
function onEditQuick(q) {
  const content = prompt('修改短语内容', q.content)
  if (content === null) return
  const group = prompt('修改分组（留空不变）', q.group_name || '常用回复')
  const payload = { content: content.trim() || undefined }
  if (group !== null) payload.group_name = group.trim() || '常用回复'
  updateQuickReply(q.id, payload)
    .then(loadQuickReplies)
    .catch((e) => alert(e.response?.data?.detail || '更新失败'))
}
async function onToggleQuick(q) {
  try {
    await updateQuickReply(q.id, { is_active: !q.is_active })
    await loadQuickReplies()
  } catch (e) {
    alert(e.response?.data?.detail || '操作失败')
  }
}
async function onDeleteQuick(q) {
  if (!confirm(`删除快捷短语「${q.content.slice(0, 20)}…」？`)) return
  try {
    await deleteQuickReply(q.id)
    await loadQuickReplies()
  } catch (e) {
    alert(e.response?.data?.detail || '删除失败')
  }
}

// ---------- 题库管理（v0.7） ----------
const qCatId = ref(null)
const questions = ref([])
const skills = ref([]) // 当前品类的知识点（绑定下拉用）
const syncingQ = ref(false)
const syncMsg = ref('')

function onTabQuestions() {
  tab.value = 'questions'
  if (!qCatId.value && matCatId.value) qCatId.value = matCatId.value
  loadQuestions()
}
async function loadQuestions() {
  if (!qCatId.value) return
  const [qRes, sRes] = await Promise.all([
    listQuestions(qCatId.value),
    listSkills(qCatId.value),
  ])
  questions.value = qRes.data
  skills.value = sRes.data
}
async function onBindSkill(q, skillId) {
  try {
    const { data } = await bindQuestionSkill(q.id, { skill_id: skillId ? Number(skillId) : null })
    q.skill_id = data.skill_id
    q.skill_name = data.skill_name
  } catch (e) {
    alert(e.response?.data?.detail || '绑定知识点失败')
  }
}
async function onBindDiff(q, difficulty) {
  try {
    const { data } = await bindQuestionSkill(q.id, { difficulty })
    q.difficulty = data.difficulty
  } catch (e) {
    alert(e.response?.data?.detail || '设置难度失败')
  }
}
async function onSyncQuestions() {
  if (!qCatId.value) return
  syncingQ.value = true
  syncMsg.value = ''
  try {
    const { data } = await syncQuestions(qCatId.value)
    syncMsg.value = data.created > 0 ? `已新建 ${data.created} 道题，当前共 ${data.total} 道` : `题目已是最新，共 ${data.total} 道`
    await loadQuestions()
  } catch (e) {
    syncMsg.value = e.response?.data?.detail || '同步失败'
  } finally {
    syncingQ.value = false
  }
}
</script>
