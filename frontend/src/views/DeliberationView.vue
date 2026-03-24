<template>
  <div class="main-view">
    <!-- Header -->
    <header class="app-header">
      <div class="header-left">
        <div class="brand" @click="router.push('/')">MIROFISH</div>
      </div>

      <div class="header-center">
        <div class="view-title">Adversarial Deliberation</div>
      </div>

      <div class="header-right">
        <div class="workflow-step">
          <span class="step-num">Council Debate</span>
          <span class="step-name">{{ statusText }}</span>
        </div>
      </div>
    </header>

    <!-- Main Content Area -->
    <main class="content-area">
      <Step4Deliberation
        :sessionId="sessionId"
        :simulationId="simulationId"
      />
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import Step4Deliberation from '../components/Step4Deliberation.vue'

const router = useRouter()
const route = useRoute()

const props = defineProps({
  sessionId: {
    type: String,
    required: true
  }
})

const simulationId = ref('')
const status = ref('loading')

const statusText = computed(() => {
  const map = {
    loading: 'Loading...',
    created: 'Session Created',
    debating: 'Debate in Progress',
    voting: 'Voting in Progress',
    synthesizing: 'Synthesizing...',
    completed: 'Completed',
    failed: 'Failed'
  }
  return map[status.value] || status.value
})

onMounted(async () => {
  try {
    const { getSession } = await import('../api/deliberation.js')
    const res = await getSession(props.sessionId)
    if (res.data) {
      simulationId.value = res.data.simulation_id
      status.value = res.data.status
    }
  } catch (e) {
    console.error('Failed to load deliberation session:', e)
    status.value = 'failed'
  }
})
</script>

<style scoped>
.main-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #0a0a0a;
  color: #e0e0e0;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  height: 48px;
  border-bottom: 1px solid #1a1a1a;
  background: #0d0d0d;
}

.header-left .brand {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 2px;
  color: #00ff88;
  cursor: pointer;
}

.header-center .view-title {
  font-size: 13px;
  color: #888;
  letter-spacing: 1px;
}

.header-right .workflow-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.step-num {
  color: #00ff88;
  font-weight: 600;
}

.step-name {
  color: #666;
}

.content-area {
  flex: 1;
  overflow: auto;
  padding: 20px;
}
</style>
