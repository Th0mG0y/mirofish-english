import service from './index'

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
  return service.post(`/api/deliberation/${sessionId}/run-debate`, { rounds })
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
  return service.post(`/api/deliberation/${sessionId}/vote`, options)
}

/**
 * Trigger synthesis
 */
export const synthesize = (sessionId) => {
  return service.post(`/api/deliberation/${sessionId}/synthesize`)
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
