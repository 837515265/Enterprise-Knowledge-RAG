const KB_BASE = "/api-knowledge/api/v1/kb"

// ======================== 知识库 ========================

export const getKnowledgeBaseList = (params) => {
  return httpGet(`${KB_BASE}/knowledge-bases`, params)
}

export const getKnowledgeBaseDetail = (kbId) => {
  return httpGet(`${KB_BASE}/knowledge-bases/${kbId}`)
}

export const createKnowledgeBase = (data) => {
  return httpPost(`${KB_BASE}/knowledge-bases`, data)
}

export const updateKnowledgeBase = (kbId, data) => {
  return httpPut(`${KB_BASE}/knowledge-bases/${kbId}`, data)
}

export const deleteKnowledgeBase = (kbId) => {
  return httpDelete(`${KB_BASE}/knowledge-bases/${kbId}`)
}

// ======================== 标签 ========================

export const getTagList = () => {
  return httpGet(`${KB_BASE}/tags`)
}

export const createTag = (data) => {
  return httpPost(`${KB_BASE}/tags`, data)
}

export const deleteTag = (tagId) => {
  return httpDelete(`${KB_BASE}/tags/${tagId}`)
}

// ======================== 策略配置 ========================

export const getParseStrategyConfigs = (params) => {
  return httpGet(`${KB_BASE}/parse-strategy-configs`, params)
}

export const createParseStrategyConfig = (data) => {
  return httpPost(`${KB_BASE}/parse-strategy-configs`, data)
}

export const updateParseStrategyConfig = (id, data) => {
  return httpPut(`${KB_BASE}/parse-strategy-configs/${id}`, data)
}

export const deleteParseStrategyConfig = (id) => {
  return httpDelete(`${KB_BASE}/parse-strategy-configs/${id}`)
}

export const getRetrievalStrategyConfigs = (params) => {
  return httpGet(`${KB_BASE}/retrieval-strategy-configs`, params)
}

export const createRetrievalStrategyConfig = (data) => {
  return httpPost(`${KB_BASE}/retrieval-strategy-configs`, data)
}

export const updateRetrievalStrategyConfig = (id, data) => {
  return httpPut(`${KB_BASE}/retrieval-strategy-configs/${id}`, data)
}

export const deleteRetrievalStrategyConfig = (id) => {
  return httpDelete(`${KB_BASE}/retrieval-strategy-configs/${id}`)
}

// ======================== 文件管理 ========================

export const getFileTree = (kbId, params) => {
  return httpGet(`${KB_BASE}/knowledge-bases/${kbId}/files`, params)
}

export const uploadFile = (kbId, data) => {
  return httpUpload(`${KB_BASE}/knowledge-bases/${kbId}/files`, data)
}

export const batchCreateKbFiles = (kbId, data) => {
  return httpPost(`${KB_BASE}/knowledge-bases/${kbId}/files`, data)
}

export const createFolder = (kbId, data) => {
  return httpPost(`${KB_BASE}/knowledge-bases/${kbId}/files/folder`, data)
}

export const updateFileNode = (kbId, fileId, data) => {
  return httpPut(`${KB_BASE}/knowledge-bases/${kbId}/files/${fileId}`, data)
}

export const moveFileNode = (kbId, fileId, data) => {
  return httpPut(`${KB_BASE}/knowledge-bases/${kbId}/files/${fileId}/move`, data)
}

export const deleteFile = (kbId, fileId) => {
  return httpDelete(`${KB_BASE}/knowledge-bases/${kbId}/files/${fileId}`)
}

export const reparseFile = (kbId, fileId) => {
  return httpPost(`${KB_BASE}/knowledge-bases/${kbId}/files/${fileId}/reparse`)
}

export const reparseAll = (kbId) => {
  return httpPost(`${KB_BASE}/knowledge-bases/${kbId}/files/reparse-all`)
}

export const reparseAllByFolder = (kbId, folderId) => {
  return httpPost(`${KB_BASE}/knowledge-bases/${kbId}/files/${folderId}/reparse-all`)
}

export const reindexKb = (kbId) => {
  return httpPost(`${KB_BASE}/knowledge-bases/${kbId}/files/reindex`)
}

export const reindexFile = (kbId, fileId) => {
  return httpPost(`${KB_BASE}/knowledge-bases/${kbId}/files/${fileId}/reindex`)
}

export const getFileKnowledgeGraph = (kbId, fileId, params) => {
  return httpGet(`${KB_BASE}/knowledge-bases/${kbId}/files/${fileId}/graph`, params)
}

export const getFileAnalysis = (kbId, fileId) => {
  return httpGet(`${KB_BASE}/knowledge-bases/${kbId}/files/${fileId}/analysis`)
}

export const getKnowledgeBaseGraph = (kbId, params) => {
  return httpGet(`${KB_BASE}/knowledge-bases/${kbId}/graph`, params)
}

export const getKnowledgeBaseGraphAudit = (kbId, params) => {
  return httpGet(`${KB_BASE}/knowledge-bases/${kbId}/graph/audit`, params)
}

export const rebuildKnowledgeBaseGraphCommunities = (kbId, params) => {
  return httpPost(`${KB_BASE}/knowledge-bases/${kbId}/graph/communities/rebuild`, null, { params })
}

// ======================== Chunk ========================

export const getChunkList = (kbId, fileId, params) => {
  return httpGet(`${KB_BASE}/knowledge-bases/${kbId}/files/${fileId}/chunks`, params)
}

export const getChunkStats = (kbId, fileId) => {
  return httpGet(`${KB_BASE}/knowledge-bases/${kbId}/files/${fileId}/chunk-stats`)
}

export const updateChunk = (kbId, chunkId, data) => {
  return httpPut(`${KB_BASE}/knowledge-bases/${kbId}/chunks/${chunkId}`, data)
}

export const toggleChunkEnabled = (kbId, chunkId, data) => {
  return httpPut(`${KB_BASE}/knowledge-bases/${kbId}/chunks/${chunkId}/enabled`, data)
}

export const deleteChunk = (kbId, chunkId) => {
  return httpDelete(`${KB_BASE}/knowledge-bases/${kbId}/chunks/${chunkId}`)
}

// ======================== 问答对 ========================

export const getQaPairList = (kbId, params) => {
  return httpGet(`${KB_BASE}/knowledge-bases/${kbId}/qa-pairs`, params)
}

export const createQaPair = (kbId, data) => {
  return httpPost(`${KB_BASE}/knowledge-bases/${kbId}/qa-pairs`, data)
}

export const updateQaPair = (kbId, qaId, data) => {
  return httpPut(`${KB_BASE}/knowledge-bases/${kbId}/qa-pairs/${qaId}`, data)
}

export const deleteQaPair = (kbId, qaId) => {
  return httpDelete(`${KB_BASE}/knowledge-bases/${kbId}/qa-pairs/${qaId}`)
}

export const importQaPairs = (kbId, data) => {
  return httpUpload(`${KB_BASE}/knowledge-bases/${kbId}/qa-pairs/import`, data)
}

export const downloadQaTemplate = (kbId) => {
  return httpDownload(`${KB_BASE}/knowledge-bases/${kbId}/qa-pairs/template`)
}

export const reindexQas = (kbId) => {
  return httpPost(`${KB_BASE}/knowledge-bases/${kbId}/qa-pairs/reindex`)
}

// ======================== 审核 ========================

export const getAuditPendingList = (params) => {
  return httpGet(`${KB_BASE}/audit/pending`, params)
}

export const getAuditHistory = (kbId, params) => {
  return httpGet(`${KB_BASE}/knowledge-bases/${kbId}/audit/history`, params)
}

export const submitFileAudit = (kbId, fileId, data) => {
  return httpPost(`${KB_BASE}/knowledge-bases/${kbId}/files/${fileId}/audit/submit`, data)
}

export const submitQaAudit = (kbId, qaId, data) => {
  return httpPost(`${KB_BASE}/knowledge-bases/${kbId}/qa-pairs/${qaId}/audit/submit`, data)
}

// ======================== 检索与问答 ========================

export const retrievalTest = (kbId, data) => {
  return httpPost(`${KB_BASE}/knowledge-bases/${kbId}/retrieval-test`, data)
}

export const retrievalTestMulti = (data) => {
  return httpPost(`${KB_BASE}/retrieval-test`, data)
}

export const getChatSessions = (params) => {
  return httpGet(`${KB_BASE}/chat/sessions`, params)
}

export const getChatMessages = (sessionId, params) => {
  return httpGet(`${KB_BASE}/chat/sessions/${sessionId}/messages`, params)
}

export const deleteChatSession = (sessionId) => {
  return httpDelete(`${KB_BASE}/chat/sessions/${sessionId}`)
}

export const updateChatMessageFeedback = (messageId, data) => {
  return httpPut(`${KB_BASE}/chat/messages/${messageId}/feedback`, data)
}

// ======================== 广场 ========================

export const getPlazaList = (params) => {
  return httpGet(`${KB_BASE}/plaza`, params)
}

export const plazaRetrieval = (kbId, data) => {
  return httpPost(`${KB_BASE}/plaza/${kbId}/retrieval`, data)
}

// ======================== 成员权限 ========================

export const getKbMembers = (kbId, params) => {
  return httpGet(`${KB_BASE}/knowledge-bases/${kbId}/members`, params)
}

export const addKbMember = (kbId, data) => {
  return httpPost(`${KB_BASE}/knowledge-bases/${kbId}/members`, data)
}

export const removeKbMember = (kbId, ruleId) => {
  return httpDelete(`${KB_BASE}/knowledge-bases/${kbId}/members/${ruleId}`)
}

// ======================== 搜文件 ========================

export const searchFiles = (params) => {
  return httpGet(`${KB_BASE}/search-files`, params)
}

// ======================== 操作日志 ========================

export const getOperationLogs = (kbId, params) => {
  return httpGet(`${KB_BASE}/knowledge-bases/${kbId}/operation-logs`, params)
}

// ======================== 解析任务 ========================

export const getParseTasks = (params) => {
  return httpGet(`${KB_BASE}/parse-tasks`, params)
}
