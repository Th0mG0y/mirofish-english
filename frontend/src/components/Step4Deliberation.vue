<template>
  <div class="deliberation-panel">
    <!-- Status Bar -->
    <div class="status-bar">
      <div class="status-info">
        <span class="status-dot" :class="session?.status || 'loading'"></span>
        <span class="status-text">{{ statusLabel }}</span>
      </div>
      <div class="action-buttons">
        <button
          v-if="canRunDebate"
          class="action-btn debate"
          :disabled="running"
          @click="startDebate"
        >
          {{ running ? 'Running...' : 'Run Debate' }}
        </button>
        <button
          v-if="canVote"
          class="action-btn vote"
          :disabled="running"
          @click="startVoting"
        >
          {{ running ? 'Voting...' : 'Conduct Voting' }}
        </button>
        <button
          v-if="canSynthesize"
          class="action-btn synthesize"
          :disabled="running"
          @click="startSynthesis"
        >
          {{ running ? 'Synthesizing...' : 'Synthesize' }}
        </button>
      </div>
    </div>

    <!-- Council Panels -->
    <div v-if="session?.rounds?.length" class="debate-area">
      <div class="councils-container">
        <!-- Optimist Council -->
        <div class="council-panel optimist">
          <h3 class="council-title optimist-title">Optimist Council</h3>
          <div class="members">
            <div v-for="m in session.optimist_council" :key="m.member_id" class="member-chip">
              {{ m.name }} <span class="member-tier">{{ m.tier }}</span>
            </div>
          </div>
          <div v-for="round in session.rounds" :key="'opt-' + round.round_number" class="round-section">
            <div class="round-label">Round {{ round.round_number }}</div>
            <div
              v-for="arg in round.arguments.filter(a => a.position === 'optimist')"
              :key="arg.member_id + '-' + arg.round_number"
              class="argument-card optimist-card"
            >
              <div class="arg-header">
                <span class="arg-member">{{ arg.member_id }}</span>
                <span class="arg-confidence">{{ (arg.confidence * 100).toFixed(0) }}%</span>
              </div>
              <div class="arg-content">{{ arg.content }}</div>
              <div v-if="arg.evidence?.length" class="arg-evidence">
                <div v-for="(ev, i) in arg.evidence" :key="i" class="evidence-item">{{ ev }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Pessimist Council -->
        <div class="council-panel pessimist">
          <h3 class="council-title pessimist-title">Pessimist Council</h3>
          <div class="members">
            <div v-for="m in session.pessimist_council" :key="m.member_id" class="member-chip">
              {{ m.name }} <span class="member-tier">{{ m.tier }}</span>
            </div>
          </div>
          <div v-for="round in session.rounds" :key="'pes-' + round.round_number" class="round-section">
            <div class="round-label">Round {{ round.round_number }}</div>
            <div
              v-for="arg in round.arguments.filter(a => a.position === 'pessimist')"
              :key="arg.member_id + '-' + arg.round_number"
              class="argument-card pessimist-card"
            >
              <div class="arg-header">
                <span class="arg-member">{{ arg.member_id }}</span>
                <span class="arg-confidence">{{ (arg.confidence * 100).toFixed(0) }}%</span>
              </div>
              <div class="arg-content">{{ arg.content }}</div>
              <div v-if="arg.evidence?.length" class="arg-evidence">
                <div v-for="(ev, i) in arg.evidence" :key="i" class="evidence-item">{{ ev }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Voting Results -->
    <div v-if="session?.vote_results?.dimensions" class="voting-section">
      <h3 class="section-title">Voting Results</h3>
      <div class="vote-dimensions">
        <div v-for="(dimData, dimName) in session.vote_results.dimensions" :key="dimName" class="dimension-card">
          <div class="dim-name">{{ dimName }}</div>
          <div class="vote-bar-container">
            <div class="vote-label-a">{{ dimData.position_a_label }}</div>
            <div class="vote-bar">
              <div
                class="bar-fill position-a"
                :style="{ width: dimData.raw_percentage.position_a + '%' }"
              >
                {{ dimData.raw_percentage.position_a }}%
              </div>
              <div
                class="bar-fill position-b"
                :style="{ width: dimData.raw_percentage.position_b + '%' }"
              >
                {{ dimData.raw_percentage.position_b }}%
              </div>
              <div
                v-if="dimData.raw_percentage.neither > 0"
                class="bar-fill neither"
                :style="{ width: dimData.raw_percentage.neither + '%' }"
              >
                {{ dimData.raw_percentage.neither }}%
              </div>
            </div>
            <div class="vote-label-b">{{ dimData.position_b_label }}</div>
          </div>
          <div class="vote-meta">
            <span>Total votes: {{ dimData.total_votes }}</span>
            <span v-if="session.vote_results.contested_dimensions?.includes(dimName)" class="contested-badge">CONTESTED</span>
            <span v-if="session.vote_results.neither_triggered?.includes(dimName)" class="neither-badge">NEITHER &gt;20%</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Synthesis -->
    <div v-if="session?.synthesis" class="synthesis-section">
      <h3 class="section-title">Synthesis</h3>
      <div class="synthesis-content" v-html="renderMarkdown(session.synthesis)"></div>
    </div>

    <!-- Empty State -->
    <div v-if="!session && !loading" class="empty-state">
      <p>No deliberation session loaded.</p>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>Loading deliberation...</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  getSession,
  runDebate,
  conductVoting,
  synthesize
} from '../api/deliberation.js'

const props = defineProps({
  sessionId: { type: String, required: true },
  simulationId: { type: String, default: '' }
})

const session = ref(null)
const loading = ref(true)
const running = ref(false)

const statusLabel = computed(() => {
  if (loading.value) return 'Loading...'
  if (!session.value) return 'No Session'
  const map = {
    created: 'Session Created — Ready for Debate',
    debating: 'Debate in Progress',
    voting: 'Voting in Progress',
    synthesizing: 'Synthesizing Results',
    completed: 'Deliberation Complete',
    failed: 'Failed'
  }
  return map[session.value.status] || session.value.status
})

const canRunDebate = computed(() => {
  return session.value && ['created', 'failed'].includes(session.value.status)
})

const canVote = computed(() => {
  return session.value && session.value.rounds?.length > 0 && !session.value.vote_results?.dimensions
})

const canSynthesize = computed(() => {
  return session.value && session.value.vote_results?.dimensions && !session.value.synthesis
})

async function loadSession() {
  loading.value = true
  try {
    const res = await getSession(props.sessionId)
    session.value = res.data
  } catch (e) {
    console.error('Failed to load session:', e)
  } finally {
    loading.value = false
  }
}

async function startDebate() {
  running.value = true
  try {
    const res = await runDebate(props.sessionId, 3)
    session.value = res.data
  } catch (e) {
    console.error('Debate failed:', e)
  } finally {
    running.value = false
  }
}

async function startVoting() {
  running.value = true
  try {
    const res = await conductVoting(props.sessionId)
    // Reload full session to get updated state
    await loadSession()
  } catch (e) {
    console.error('Voting failed:', e)
  } finally {
    running.value = false
  }
}

async function startSynthesis() {
  running.value = true
  try {
    await synthesize(props.sessionId)
    await loadSession()
  } catch (e) {
    console.error('Synthesis failed:', e)
  } finally {
    running.value = false
  }
}

function renderMarkdown(text) {
  if (!text) return ''
  // Basic markdown rendering
  return text
    .replace(/### (.*)/g, '<h4>$1</h4>')
    .replace(/## (.*)/g, '<h3>$1</h3>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
}

onMounted(() => {
  loadSession()
})
</script>

<style scoped>
.deliberation-panel {
  max-width: 1400px;
  margin: 0 auto;
}

.status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #111;
  border: 1px solid #222;
  border-radius: 8px;
  margin-bottom: 16px;
}

.status-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #444;
}
.status-dot.created { background: #666; }
.status-dot.debating { background: #f0a030; animation: pulse 1.5s infinite; }
.status-dot.voting { background: #3090f0; animation: pulse 1.5s infinite; }
.status-dot.synthesizing { background: #a060f0; animation: pulse 1.5s infinite; }
.status-dot.completed { background: #00ff88; }
.status-dot.failed { background: #ff4444; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.action-buttons {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 6px 14px;
  font-size: 12px;
  border: 1px solid #333;
  border-radius: 4px;
  background: #1a1a1a;
  color: #ccc;
  cursor: pointer;
  transition: all 0.2s;
}
.action-btn:hover:not(:disabled) { background: #252525; border-color: #555; }
.action-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.action-btn.debate { border-color: #f0a030; color: #f0a030; }
.action-btn.vote { border-color: #3090f0; color: #3090f0; }
.action-btn.synthesize { border-color: #a060f0; color: #a060f0; }

/* Councils */
.debate-area {
  margin-bottom: 24px;
}

.councils-container {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.council-panel {
  background: #0d0d0d;
  border: 1px solid #1a1a1a;
  border-radius: 8px;
  padding: 16px;
}

.council-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #1a1a1a;
}
.optimist-title { color: #00cc66; }
.pessimist-title { color: #ff5555; }

.members {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.member-chip {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 3px;
  background: #151515;
  border: 1px solid #222;
  color: #999;
}

.member-tier {
  color: #555;
  margin-left: 4px;
}

.round-section {
  margin-bottom: 12px;
}

.round-label {
  font-size: 11px;
  color: #555;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 6px;
}

.argument-card {
  background: #111;
  border: 1px solid #1a1a1a;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 8px;
}

.optimist-card { border-left: 3px solid #00cc66; }
.pessimist-card { border-left: 3px solid #ff5555; }

.arg-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: 11px;
}

.arg-member { color: #888; }
.arg-confidence { color: #666; }

.arg-content {
  font-size: 13px;
  line-height: 1.6;
  color: #ccc;
}

.arg-evidence {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #1a1a1a;
}

.evidence-item {
  font-size: 11px;
  color: #777;
  padding: 2px 0;
}
.evidence-item::before {
  content: '\2022 ';
  color: #444;
}

/* Voting */
.voting-section, .synthesis-section {
  margin-bottom: 24px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #aaa;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #1a1a1a;
}

.vote-dimensions {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dimension-card {
  background: #0d0d0d;
  border: 1px solid #1a1a1a;
  border-radius: 8px;
  padding: 14px;
}

.dim-name {
  font-size: 13px;
  font-weight: 600;
  color: #ccc;
  margin-bottom: 8px;
}

.vote-bar-container {
  display: flex;
  align-items: center;
  gap: 8px;
}

.vote-label-a, .vote-label-b {
  font-size: 11px;
  color: #777;
  min-width: 100px;
}
.vote-label-b { text-align: right; }

.vote-bar {
  flex: 1;
  display: flex;
  height: 24px;
  border-radius: 4px;
  overflow: hidden;
  background: #1a1a1a;
}

.bar-fill {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 600;
  color: #fff;
  min-width: 30px;
}
.bar-fill.position-a { background: #00996644; color: #00cc88; }
.bar-fill.position-b { background: #ff444444; color: #ff6666; }
.bar-fill.neither { background: #66666644; color: #999; }

.vote-meta {
  display: flex;
  gap: 12px;
  margin-top: 6px;
  font-size: 11px;
  color: #555;
}

.contested-badge {
  background: #f0a03022;
  color: #f0a030;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
}

.neither-badge {
  background: #a060f022;
  color: #a060f0;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
}

/* Synthesis */
.synthesis-content {
  background: #0d0d0d;
  border: 1px solid #1a1a1a;
  border-radius: 8px;
  padding: 20px;
  font-size: 13px;
  line-height: 1.7;
  color: #ccc;
}

/* Empty / Loading */
.empty-state, .loading-state {
  text-align: center;
  padding: 60px 20px;
  color: #555;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid #333;
  border-top-color: #00ff88;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 12px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
