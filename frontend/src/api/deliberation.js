import service from './index'

// Deliberation operations can take 10+ minutes (3 rounds of LLM debate + web search)
const DELIBERATION_TIMEOUT = 3600000 // 1 hour

/**
 * Create a new deliberation session
 */
export const createDeliberation = (data) => {
  return service.post('/api/deliberation/create', data)
}

/**
 * Run the structured debate
 */
export const runDebate = (sessionId, rounds = 3) => {
  return service.post(`/api/deliberation/${sessionId}/run-debate`, { rounds }, { timeout: DELIBERATION_TIMEOUT })
}

/**
 * Get deliberation status
 */
export const getDeliberationStatus = (sessionId) => {
  return service.get(`/api/deliberation/${sessionId}/status`)
}

/**
 * Conduct multi-dimensional voting
 */
export const conductVoting = (sessionId, options = {}) => {
  return service.post(`/api/deliberation/${sessionId}/vote`, options, { timeout: DELIBERATION_TIMEOUT })
}

/**
 * Trigger synthesis
 */
export const synthesize = (sessionId) => {
  return service.post(`/api/deliberation/${sessionId}/synthesize`, {}, { timeout: DELIBERATION_TIMEOUT })
}

/**
 * Get full session data
 */
export const getSession = (sessionId) => {
  return service.get(`/api/deliberation/${sessionId}`)
}

/**
 * Get deliberation trace
 */
export const getTrace = (sessionId) => {
  return service.get(`/api/deliberation/${sessionId}/trace`)
}

/**
 * Get deliberation by simulation ID
 */
export const getBySimulation = (simulationId) => {
  return service.get(`/api/deliberation/by-simulation/${simulationId}`)
}
