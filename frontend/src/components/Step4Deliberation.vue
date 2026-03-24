<template>
  <div class="deliberation-panel">
    <!-- Status Bar -->
    <div class="status-bar">
      <div class="status-info">
        <span class="status-dot" :class="currentPhase"></span>
        <span class="status-text">{{ statusLabel }}</span>
      </div>
      <div class="action-buttons">
        <button
          v-if="canRunDebate"
          class="action-btn debate"
          :disabled="running"
          @click="startDebate"
        >
          {{ running && currentPhase === 'debating' ? 'Running...' : 'Run Debate' }}
        </button>
        <button
          v-if="canVote"
          class="action-btn vote"
          :disabled="running"
          @click="startVoting"
        >
          {{ running && currentPhase === 'voting' ? 'Voting...' : 'Conduct Voting' }}
        </button>
        <button
          v-if="canSynthesize"
          class="action-btn synthesize"
          :disabled="running"
          @click="startSynthesis"
        >
          {{ running && currentPhase === 'synthesizing' ? 'Synthesizing...' : 'Synthesize' }}
        </button>
      </div>
    </div>

    <!-- Phase Progress -->
    <div v-if="running" class="phase-progress">
      <div class="progress-spinner"></div>
      <span class="progress-text">{{ phaseProgressText }}</span>
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

    <!-- Error State -->
    <div v-if="errorMessage" class="error-banner">
      <div class="error-content">
        <span class="error-icon">!</span>
        <span class="error-text">{{ errorMessage }}</span>
      </div>
      <p class="error-hint">You can go back to the simulation and generate the report from there, or retry the debate.</p>
    </div>

    <!-- Navigation Buttons (always visible when session loaded) -->
    <div v-if="session && !loading" class="navigation-section">
      <button class="nav-btn secondary" @click="backToSimulation" :disabled="running">
        Back to Simulation
      </button>
      <button v-if="isComplete" class="nav-btn primary" :disabled="generatingReport" @click="handleGenerateReport">
        {{ generatingReport ? 'Creating Report...' : 'Generate Report' }}
      </button>
    </div>

    <!-- Empty State -->
    <div v-if="!session && !loading" class="empty-state">
      <p>No deliberation session loaded.</p>
      <button class="nav-btn secondary" style="margin-top: 12px" @click="backToSimulation">
        Back to Simulation
      </button>
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
import { useRouter } from 'vue-router'
import {
  getSession,
  runDebate,
  conductVoting,
  synthesize
} from '../api/deliberation.js'
import { generateReport } from '../api/report.js'

const router = useRouter()

const props = defineProps({
  sessionId: { type: String, required: true },
  simulationId: { type: String, default: '' }
})

const emit = defineEmits(['update-status'])

const session = ref(null)
const loading = ref(true)
const running = ref(false)
const currentPhase = ref('idle') // idle | debating | voting | synthesizing | done
const generatingReport = ref(false)
const errorMessage = ref('')

function notify(title, body) {
  if (!('Notification' in window)) return
  if (Notification.permission === 'granted') {
    new Notification(title, { body, icon: '/favicon.ico' })
  } else if (Notification.permission !== 'denied') {
    Notification.requestPermission().then(perm => {
      if (perm === 'granted') new Notification(title, { body, icon: '/favicon.ico' })
    })
  }
}

const statusLabel = computed(() => {
  if (loading.value) return 'Loading...'
  if (!session.value) return 'No Session'
  if (running.value) {
    const map = {
      debating: 'Debate in Progress...',
      voting: 'Voting in Progress...',
      synthesizing: 'Synthesizing Results...'
    }
    return map[currentPhase.value] || 'Processing...'
  }
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

const phaseProgressText = computed(() => {
  const map = {
    debating: 'Running 3 debate rounds — this may take a few minutes...',
    voting: 'Conducting multi-dimensional voting across all council members...',
    synthesizing: 'Generating synthesis from debate and voting results...'
  }
  return map[currentPhase.value] || 'Processing...'
})

const canRunDebate = computed(() => {
  if (!session.value) return false
  return ['created', 'failed'].includes(session.value.status)
})

const canVote = computed(() => {
  return session.value && session.value.rounds?.length > 0 && !session.value.vote_results?.dimensions
})

const canSynthesize = computed(() => {
  return session.value && session.value.vote_results?.dimensions && !session.value.synthesis
})

const isComplete = computed(() => {
  // Complete when synthesis exists, or when debate is done and user could skip ahead
  return session.value?.synthesis != null
})

async function loadSession() {
  loading.value = true
  try {
    const res = await getSession(props.sessionId)
    session.value = res.data
    // Set phase based on existing session state
    if (session.value) {
      if (session.value.synthesis) {
        currentPhase.value = 'done'
        emit('update-status', 'completed')
      } else if (session.value.vote_results?.dimensions) {
        currentPhase.value = 'idle'
        emit('update-status', 'idle')
      } else if (session.value.rounds?.length > 0) {
        currentPhase.value = 'idle'
        emit('update-status', 'idle')
      } else {
        currentPhase.value = 'idle'
        emit('update-status', 'idle')
      }
    }
  } catch (e) {
    console.error('Failed to load session:', e)
    emit('update-status', 'error')
  } finally {
    loading.value = false
  }
}

async function startDebate() {
  running.value = true
  currentPhase.value = 'debating'
  errorMessage.value = ''
  emit('update-status', 'debating')
  try {
    const res = await runDebate(props.sessionId, 3)
    session.value = res.data
    currentPhase.value = 'idle'
    emit('update-status', 'idle')
    notify('Debate Complete', 'All 3 debate rounds have finished. Ready for voting.')
  } catch (e) {
    console.error('Debate failed:', e)
    currentPhase.value = 'idle'
    emit('update-status', 'error')
    errorMessage.value = e?.response?.data?.error || e?.message || 'The debate failed. You can retry or go back to generate the report from the simulation.'
    notify('Debate Failed', 'An error occurred during the debate.')
    // Reload session to get latest state (may have partial results)
    await loadSession()
  } finally {
    running.value = false
  }
}

async function startVoting() {
  running.value = true
  currentPhase.value = 'voting'
  errorMessage.value = ''
  emit('update-status', 'voting')
  try {
    await conductVoting(props.sessionId)
    await loadSession()
    notify('Voting Complete', 'Multi-dimensional voting has finished. Ready for synthesis.')
  } catch (e) {
    console.error('Voting failed:', e)
    currentPhase.value = 'idle'
    emit('update-status', 'error')
    errorMessage.value = e?.response?.data?.error || e?.message || 'Voting failed.'
    notify('Voting Failed', 'An error occurred during voting.')
  } finally {
    running.value = false
  }
}

async function startSynthesis() {
  running.value = true
  currentPhase.value = 'synthesizing'
  errorMessage.value = ''
  emit('update-status', 'synthesizing')
  try {
    await synthesize(props.sessionId)
    await loadSession()
    notify('Synthesis Complete', 'Deliberation is complete. You can now generate a report.')
  } catch (e) {
    console.error('Synthesis failed:', e)
    currentPhase.value = 'idle'
    emit('update-status', 'error')
    errorMessage.value = e?.response?.data?.error || e?.message || 'Synthesis failed.'
    notify('Synthesis Failed', 'An error occurred during synthesis.')
  } finally {
    running.value = false
  }
}

function backToSimulation() {
  const simId = props.simulationId || session.value?.simulation_id
  if (simId) {
    router.push(`/simulation/${simId}/start`)
  } else {
    router.push('/')
  }
}

async function handleGenerateReport() {
  const simId = props.simulationId || session.value?.simulation_id
  if (!simId) return

  generatingReport.value = true
  try {
    const res = await generateReport({ simulation_id: simId })
    if (res.success && res.data?.report_id) {
      router.push({ name: 'Report', params: { reportId: res.data.report_id } })
    } else {
      console.error('Failed to create report:', res.error)
    }
  } catch (e) {
    console.error('Report generation failed:', e)
  } finally {
    generatingReport.value = false
  }
}

function renderMarkdown(text) {
  if (!text) return ''
  return text
    .replace(/### (.*)/g, '<h4>$1</h4>')
    .replace(/## (.*)/g, '<h3>$1</h3>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
}

onMounted(() => {
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission()
  }
  loadSession()
})
</script>

<style scoped>
.deliberation-panel {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
}

/* Status Bar */
.status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #F8F9FA;
  border: 1px solid #EAEAEA;
  border-radius: 8px;
  margin-bottom: 16px;
}

.status-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #333;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #CCC;
}
.status-dot.idle { background: #999; }
.status-dot.debating { background: #FF9800; animation: pulse 1.5s infinite; }
.status-dot.voting { background: #2196F3; animation: pulse 1.5s infinite; }
.status-dot.synthesizing { background: #9C27B0; animation: pulse 1.5s infinite; }
.status-dot.done { background: #4CAF50; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Phase Progress */
.phase-progress {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: #FFF8E1;
  border: 1px solid #FFE082;
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 13px;
  color: #5D4037;
}

.progress-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid #FFE082;
  border-top-color: #FF9800;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.progress-text {
  font-weight: 500;
}

/* Action Buttons */
.action-buttons {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 600;
  border: 1px solid #DDD;
  border-radius: 6px;
  background: #FFF;
  color: #333;
  cursor: pointer;
  transition: all 0.2s;
}
.action-btn:hover:not(:disabled) { background: #F5F5F5; border-color: #BBB; }
.action-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.action-btn.debate { border-color: #FF9800; color: #E65100; }
.action-btn.debate:hover:not(:disabled) { background: #FFF3E0; }
.action-btn.vote { border-color: #2196F3; color: #1565C0; }
.action-btn.vote:hover:not(:disabled) { background: #E3F2FD; }
.action-btn.synthesize { border-color: #9C27B0; color: #7B1FA2; }
.action-btn.synthesize:hover:not(:disabled) { background: #F3E5F5; }

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
  background: #FFF;
  border: 1px solid #EAEAEA;
  border-radius: 8px;
  padding: 16px;
}

.council-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #EAEAEA;
}
.optimist-title { color: #2E7D32; }
.pessimist-title { color: #C62828; }

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
  background: #F5F5F5;
  border: 1px solid #E0E0E0;
  color: #555;
}

.member-tier {
  color: #999;
  margin-left: 4px;
}

.round-section {
  margin-bottom: 12px;
}

.round-label {
  font-size: 11px;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 6px;
}

.argument-card {
  background: #FAFAFA;
  border: 1px solid #EAEAEA;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 8px;
}

.optimist-card { border-left: 3px solid #4CAF50; }
.pessimist-card { border-left: 3px solid #F44336; }

.arg-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: 11px;
}

.arg-member { color: #666; }
.arg-confidence { color: #999; }

.arg-content {
  font-size: 13px;
  line-height: 1.6;
  color: #333;
}

.arg-evidence {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #EAEAEA;
}

.evidence-item {
  font-size: 11px;
  color: #777;
  padding: 2px 0;
}
.evidence-item::before {
  content: '\2022 ';
  color: #BBB;
}

/* Voting */
.voting-section, .synthesis-section {
  margin-bottom: 24px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #EAEAEA;
}

.vote-dimensions {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dimension-card {
  background: #FFF;
  border: 1px solid #EAEAEA;
  border-radius: 8px;
  padding: 14px;
}

.dim-name {
  font-size: 13px;
  font-weight: 600;
  color: #333;
  margin-bottom: 8px;
}

.vote-bar-container {
  display: flex;
  align-items: center;
  gap: 8px;
}

.vote-label-a, .vote-label-b {
  font-size: 11px;
  color: #666;
  min-width: 100px;
}
.vote-label-b { text-align: right; }

.vote-bar {
  flex: 1;
  display: flex;
  height: 24px;
  border-radius: 4px;
  overflow: hidden;
  background: #F0F0F0;
}

.bar-fill {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 600;
  color: #FFF;
  min-width: 30px;
}
.bar-fill.position-a { background: #66BB6A; color: #FFF; }
.bar-fill.position-b { background: #EF5350; color: #FFF; }
.bar-fill.neither { background: #BDBDBD; color: #FFF; }

.vote-meta {
  display: flex;
  gap: 12px;
  margin-top: 6px;
  font-size: 11px;
  color: #999;
}

.contested-badge {
  background: #FFF3E0;
  color: #E65100;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
}

.neither-badge {
  background: #F3E5F5;
  color: #7B1FA2;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
}

/* Synthesis */
.synthesis-content {
  background: #FFF;
  border: 1px solid #EAEAEA;
  border-radius: 8px;
  padding: 20px;
  font-size: 13px;
  line-height: 1.7;
  color: #333;
}

/* Navigation */
.navigation-section {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 0;
  border-top: 1px solid #EAEAEA;
  margin-top: 8px;
}

.nav-btn {
  padding: 10px 20px;
  font-size: 13px;
  font-weight: 600;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.nav-btn.secondary {
  background: #FFF;
  border: 1px solid #DDD;
  color: #555;
}
.nav-btn.secondary:hover { background: #F5F5F5; border-color: #BBB; }

.nav-btn.primary {
  background: #1976D2;
  border: 1px solid #1565C0;
  color: #FFF;
}
.nav-btn.primary:hover:not(:disabled) { background: #1565C0; }
.nav-btn.primary:disabled { opacity: 0.5; cursor: not-allowed; }

/* Empty / Loading */
.empty-state, .loading-state {
  text-align: center;
  padding: 60px 20px;
  color: #999;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid #E0E0E0;
  border-top-color: #1976D2;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 12px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Error Banner */
.error-banner {
  background: #FFF5F5;
  border: 1px solid #FFCDD2;
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 16px;
}

.error-content {
  display: flex;
  align-items: center;
  gap: 10px;
}

.error-icon {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #F44336;
  color: #FFF;
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.error-text {
  font-size: 13px;
  color: #C62828;
  font-weight: 500;
}

.error-hint {
  font-size: 12px;
  color: #999;
  margin: 8px 0 0 32px;
}
</style>
