<template>
  <div class="kb-page kb-detail-page" style="padding: 12px 16px 24px">
    <div class="kb-page-inner kb-page-inner--full">
      <!-- 面包屑 -->
      <p class="kb-page-desc" style="margin-bottom: 8px">
        <router-link to="/knowledge/list" style="font-weight: 600; color: #2563eb">我的知识库</router-link>
        <span style="color: #cbd5e1"> / </span>
        <span style="font-weight: 600">{{ kbInfo?.name || "加载中…" }}</span>
      </p>

      <!-- V2 主布局 -->
      <div
        class="kd-v2"
        :style="{ '--kd-sidebar-width': `${sidebarWidth}px` }"
      >
        <!-- 左栏 -->
        <aside class="kd-v2-sidebar">
          <div class="kd-v2-sidebar-head">
            <span>知识库</span>
          </div>

          <!-- 库选择器 -->
          <div class="kd-v2-select">
            <span class="kd-v2-select-thumb">
              <a-icon :type="getKnowledgeTypeIcon(kbInfo?.type)" />
            </span>
            <span class="kd-v2-select-label">{{ kbInfo?.name || "…" }}</span>
          </div>

          <!-- 问AI按钮 -->
          <button type="button" class="kd-v2-ask-btn" :class="{ 'is-active': stage === 'ask' }" @click="stage = 'ask'">
            <a-icon type="message" />
            问AI
          </button>

          <!-- 工具栏 -->
          <div v-if="canManageFiles" class="kd-v2-toolbar">
            <button type="button" class="kd-v2-add" @click="openUploadModal()">＋ 添加文件</button>
          </div>

          <!-- 知识目录 -->
          <div class="kd-v2-tree-head">
            <span>知识目录</span>
          </div>
          <a-input
            v-model="fileSearchKeyword"
            class="kd-v2-tree-search"
            allow-clear
            size="small"
            placeholder="搜索当前目录文件"
          >
            <a-icon slot="prefix" type="search" />
          </a-input>
          <div
            class="kd-v2-tree"
            :class="{ 'is-drag-over-root': dragOverRoot }"
            @dragover.prevent="onTreeRootDragOver"
            @dragleave="onTreeRootDragLeave"
            @drop.prevent="onDropToRoot"
          >
            <!-- 系统根节点：知识库全局图谱 -->
            <div
              class="kd-tree-row kd-tree-row--system"
              :class="{ 'is-active': stage === 'graph' }"
              @click="stage = 'graph'"
            >
              <div class="kd-tree-label">
                <span class="kd-tree-toggle kd-tree-toggle--placeholder"></span>
                <span class="kd-tree-icon is-system is-graph-root">
                  <a-icon type="share-alt" />
                </span>
                <span class="kd-tree-name">知识库全局图谱</span>
              </div>
              <span class="kd-tree-scope">KB</span>
            </div>

            <!-- 系统根节点：知识库问答对 -->
            <div
              class="kd-tree-row kd-tree-row--system"
              :class="{ 'is-active': stage === 'qa-root' }"
              @click="stage = 'qa-root'"
            >
              <div class="kd-tree-label">
                <span class="kd-tree-toggle kd-tree-toggle--placeholder"></span>
                <span class="kd-tree-icon is-system">
                  <a-icon type="message" />
                </span>
                <span class="kd-tree-name">知识库问答对</span>
              </div>
              <span v-if="canReviewContent && pendingQaCount > 0" class="kd-tree-pending-dot">{{
                pendingQaCount
              }}</span>
              <span class="kd-tree-lock" title="系统节点">
                <a-icon type="lock" />
              </span>
            </div>

            <!-- 系统根节点：知识库文件管理 -->
            <div class="kd-tree-row kd-tree-row--system" @click="fileRootExpanded = !fileRootExpanded">
              <div class="kd-tree-label">
                <button
                  type="button"
                  class="kd-tree-toggle"
                  :class="{ 'is-open': fileRootExpanded }"
                  @click.stop="fileRootExpanded = !fileRootExpanded"
                >
                  <a-icon type="caret-right" />
                </button>
                <span class="kd-tree-icon is-system is-file-root">
                  <a-icon :type="fileRootExpanded ? 'folder-open' : 'folder'" />
                </span>
                <span class="kd-tree-name">知识库文件管理</span>
              </div>
              <a-dropdown v-if="canManageFiles" :trigger="['click']" @click.native.stop>
                <button type="button" class="kd-tree-root-add" title="添加文件或目录" @click.stop>
                  <a-icon type="plus" />
                </button>
                <template #overlay>
                  <a-menu @click="handleFileRootMenuClick">
                    <a-menu-item key="upload"><a-icon type="cloud-upload" /> 上传文件</a-menu-item>
                    <a-menu-item key="create-folder"><a-icon type="folder-add" /> 创建目录</a-menu-item>
                    <a-menu-item key="reparse-all"><a-icon type="reload" /> 重新解析全部</a-menu-item>
                    <a-menu-item key="reindex"><a-icon type="database" /> 重新索引全部</a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
            </div>

            <!-- 文件树 -->
            <transition-group
              v-if="fileRootExpanded"
              name="kd-tree-list"
              tag="div"
              class="kd-tree-list kd-tree-list--files"
            >
              <div
                v-for="item in visibleFileTree"
                :key="item.id"
                class="kd-tree-row"
                :class="{
                  'kd-tree-row--folder': item.isFolder,
                  'kd-tree-row--file': !item.isFolder,
                  'is-dragging': draggingNodeId === item.id,
                  'is-drag-over': dragOverFolderId === item.id,
                  'is-active': stage === 'file' && selectedFileId === item.id
                }"
                :style="{ paddingLeft: `${18 + (item.level || 0) * 16}px` }"
                :draggable="canManageFiles"
                @dragstart.stop="onNodeDragStart(item, $event)"
                @dragend="onNodeDragEnd"
                @dragover.prevent.stop="onNodeDragOver(item)"
                @dragleave.stop="onNodeDragLeave(item)"
                @drop.prevent.stop="onDropToNode(item)"
                @click="selectFile(item)"
                @contextmenu.prevent.stop="openContextMenu(item, $event)"
              >
                <div class="kd-tree-label">
                  <button
                    v-if="item.isFolder"
                    type="button"
                    class="kd-tree-toggle"
                    :class="{ 'is-open': isFolderExpanded(item.id) }"
                    @click.stop="toggleFolder(item)"
                  >
                    <a-icon type="caret-right" />
                  </button>
                  <span v-else class="kd-tree-toggle kd-tree-toggle--placeholder"></span>
                  <span class="kd-tree-icon" :class="{ 'is-folder': item.isFolder, 'is-file': !item.isFolder }">
                    <a-icon :type="treeIconType(item)" />
                  </span>
                  <span class="kd-tree-name" :title="item.name">{{ item.name }}</span>
                </div>
                <a-tooltip v-if="!item.isFolder" :title="fileTreeStateText(item)">
                  <span class="kd-tree-file-state" :class="`is-${item.parseStatus || 'none'}`"></span>
                </a-tooltip>
                <a-dropdown v-if="canManageFiles || !item.isFolder" :trigger="['click']" @click.native.stop>
                  <span class="kd-tree-more" @click.stop>⋯</span>
                  <template #overlay>
                    <a-menu @click="handleTreeMenuClick(item, $event)">
                      <a-menu-item v-if="canManageFiles && item.isFolder" key="upload">上传到此目录</a-menu-item>
                      <a-menu-item v-if="canManageFiles && item.isFolder" key="create-child">新建子目录</a-menu-item>
                      <a-menu-item v-if="canManageFiles && item.isFolder" key="reparse-all">重新解析此目录</a-menu-item>
                      <a-menu-item v-if="canManageFiles" key="rename">重命名</a-menu-item>
                      <a-menu-item v-if="!item.isFolder" key="download">下载</a-menu-item>
                      <a-menu-item v-if="canManageFiles && !item.isFolder" key="reparse">重新解析</a-menu-item>
                      <a-menu-item v-if="canManageFiles && !item.isFolder && item.parseStatus === 'parsed'" key="reindex">重新索引</a-menu-item>
                      <a-menu-item v-if="canManageFiles" key="delete">
                        <span class="text-red-500">删除</span>
                      </a-menu-item>
                    </a-menu>
                  </template>
                </a-dropdown>
              </div>
            </transition-group>

            <div v-if="fileRootExpanded && !fileTree.length" class="kd-tree-empty">
              <div class="kd-tree-empty__text">暂无文件内容</div>
              <div class="kd-tree-empty__actions">
                <button type="button" @click="openUploadModal(null)">上传文件</button>
                <span>或</span>
                <button type="button" @click="onCreateFolder(null)">创建目录</button>
              </div>
            </div>
          </div>

          <!-- 底部按钮 -->
          <div v-if="canManageSettings" class="kd-v2-sidebar-foot">
            <button type="button" class="kd-v2-foot-btn" @click="showSettings = true">设置</button>
          </div>
        </aside>

        <div class="kd-v2-resizer" title="拖拽调整左侧宽度" @mousedown.prevent="startSidebarResize"></div>

        <!-- 右侧主区 -->
        <div class="kd-v2-main">
          <!-- Stage: 问AI -->
          <section v-show="stage === 'ask'" class="kd-v2-stage kd-v2-stage--chat">
            <div class="kd-v2-stage-inner kd-v2-stage-inner--chat">
              <KnowledgeChatPanel embedded :fixed-kb-id="currentKbId" :fixed-kb-name="kbInfo?.name" />
            </div>
          </section>

          <!-- Stage: 问答对根节点 -->
          <section v-show="stage === 'qa-root'" class="kd-v2-stage kd-v2-stage--qa">
            <div class="kd-v2-file-head">
              <div>
                <h2 class="kd-v2-file-title">知识库问答对</h2>
              </div>
              <button
                class="kb-btn-sm primary"
                @click="
                  showSettings = true
                  settingsTab = 'qa'
                "
              >
                <a-icon type="setting" /> 在设置中管理
              </button>
            </div>
            <div class="kd-v2-qa-list">
              <QaList
                :kb-id="currentKbId"
                :compact="true"
                :can-audit="canReviewContent"
                :can-manage="canManageFiles"
                :initial-audit-status="canReviewContent && pendingQaCount > 0 ? 'pending' : undefined"
                @audited="refreshAuditIndicators"
              />
            </div>
          </section>

          <!-- Stage: 知识库全局图谱 -->
          <section v-show="stage === 'graph'" class="kd-v2-stage kd-v2-stage--graph">
            <KbKnowledgeGraphPanel :kb-id="currentKbId" :kb-name="kbInfo?.name" />
          </section>

          <!-- Stage: 文件预览 -->
          <section v-show="stage === 'file'" class="kd-v2-stage">
            <template v-if="selectedFile">
              <div class="kd-v2-file-head">
                <div class="kd-v2-file-title-wrap">
                  <button type="button" class="kd-v2-file-back" title="返回知识库全局图谱" @click="backToKbOverview">
                    <a-icon type="left" />
                  </button>
                  <div class="kd-v2-file-title-main">
                    <div class="kd-v2-file-title-line">
                      <h2 class="kd-v2-file-title">{{ selectedFile.name }}</h2>
                      <span class="kd-v2-file-status" :class="`is-${selectedFile.parseStatus || 'none'}`">
                        {{ fileParseStatusText(selectedFile.parseStatus) }}
                      </span>
                    </div>
                    <div class="kd-v2-file-subline">
                      <p class="kd-v2-file-meta">
                        {{ selectedFile.createName || "" }} · {{ selectedFile.updateTime || "" }}
                      </p>
                      <div v-if="selectedFile.parseStatus === 'parsed'" class="kd-v2-file-metrics">
                        <button @click="openKnowledgeTab('content')"><strong>{{ documentOverview.chunkCount }}</strong> Chunk</button>
                        <button v-if="documentOverview.imageCount" @click="openKnowledgeTab('multimodal')"><strong>{{ documentOverview.imageCount }}</strong> 图片</button>
                        <button v-if="documentOverview.flowCount" @click="openKnowledgeTab('multimodal')"><strong>{{ documentOverview.flowCount }}</strong> 流程</button>
                        <button v-if="documentOverview.entityCount" @click="openKnowledgeTab('graph')"><strong>{{ documentOverview.entityCount }}</strong> 实体</button>
                        <button v-if="documentOverview.relationCount" @click="openKnowledgeTab('graph')"><strong>{{ documentOverview.relationCount }}</strong> 关系</button>
                      </div>
                    </div>
                    <p
                      v-if="selectedFile.parseStatus === 'failed' && selectedFile.parseErrorMsg"
                      class="kd-v2-file-error"
                    >
                      失败原因：{{ selectedFile.parseErrorMsg }}
                    </p>
                  </div>
                </div>
                <div class="flex flex-wrap items-center gap-2">
                  <button v-if="canManageFiles" class="kb-btn-sm" @click="onReparseFile(selectedFile)"><a-icon type="sync" /> 重新解析</button>
                  <button class="kb-btn-sm" title="下载" @click="onDownloadFile(selectedFile)"><a-icon type="download" /> 下载</button>
                </div>
              </div>

              <div class="kd-v2-file-workspace" :class="{ 'is-parse-mode': showParsePanel }">
                <!-- 文件预览区 -->
                <div class="kd-v2-preview">
                  <FilePreview
                    v-if="selectedFile.fileId"
                    :key="selectedFile.fileId"
                    class="kd-v2-preview-file"
                    :file-id="String(selectedFile.fileId)"
                    :highlight-block-ids="selectedPreviewBlockIds"
                    :highlight-page="selectedPreviewPage"
                    hide-download-button
                  />
                  <div v-else class="kd-v2-preview-placeholder">
                    <p>文件预览区</p>
                    <small>当前文件缺少可预览的文件ID</small>
                  </div>
                </div>

                <!-- 文档知识工作区 -->
                <transition name="kd-parse-slide">
                  <div v-if="showParsePanel" class="kd-parse-panel">
                    <DocumentKnowledgePanel
                      v-if="selectedFile.parseStatus === 'parsed'"
                      ref="knowledgePanelRef"
                      :kb-id="currentKbId"
                      :file-id="selectedFile.id"
                      :file-name="selectedFile.name"
                      :can-edit="canManageFiles"
                      :can-audit="canReviewContent"
                      :active-chunk-id="selectedPreviewChunkId"
                      @locate="onSelectChunkForPreview"
                      @overview="onDocumentOverview"
                      @edited="onChunkEdited"
                      @audited="refreshAuditIndicators"
                    />
                  </div>
                </transition>
              </div>
            </template>
            <div v-else class="kd-v2-preview">
              <div class="kd-v2-preview-placeholder">
                <p>请从左侧目录选择一个文件</p>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>

    <!-- 设置抽屉 -->
    <div v-if="showSettings" class="kd-drawer" @click.self="showSettings = false">
      <div class="kd-drawer-panel" @click.stop>
        <div class="kd-drawer-head">
          <h2>知识库设置</h2>
          <button type="button" class="kd-drawer-close" @click="showSettings = false">×</button>
        </div>
        <div class="kd-drawer-body">
          <nav class="kd-drawer-rail">
            <button
              v-for="tab in settingsTabs"
              :key="tab.key"
              type="button"
              :class="{ 'is-active': settingsTab === tab.key }"
              @click="settingsTab = tab.key"
            >
              <span class="kd-drawer-rail-icon">
                <a-icon :type="tab.icon" />
              </span>
              <span class="kd-drawer-rail-text">
                <span>{{ tab.label }}</span>
                <small>{{ tab.desc }}</small>
              </span>
            </button>
          </nav>
          <div class="kd-drawer-stage">
            <QaList
              v-if="settingsTab === 'qa'"
              :kb-id="currentKbId"
              :can-audit="canReviewContent"
              :can-manage="canManageFiles"
              @audited="refreshAuditIndicators"
            />
            <RetrievalTest v-else-if="settingsTab === 'search'" :kb-id="currentKbId" />
            <AuditManage v-else-if="settingsTab === 'audit'" :kb-id="currentKbId" />
            <MemberManage v-else-if="settingsTab === 'members'" :kb-id="currentKbId" :kb-info="kbInfo" />
            <KbSettingsForm
              v-else-if="settingsTab === 'settings'"
              :kb-id="currentKbId"
              :kb-info="kbInfo"
              @saved="loadKbDetail"
            />
            <KbStrategySettingsForm
              v-else-if="settingsTab === 'strategy'"
              :kb-id="currentKbId"
              :kb-info="kbInfo"
              @saved="loadKbDetail"
            />
            <OperationLog v-else-if="settingsTab === 'log'" :kb-id="currentKbId" />
          </div>
        </div>
      </div>
    </div>

    <a-modal
      v-model="showUploadModal"
      :width="720"
      :confirm-loading="uploadSubmitting"
      ok-text="上传并开始解析"
      cancel-text="取消"
      destroy-on-close
      wrap-class-name="kb-upload-dialog"
      @ok="submitUploadBatch"
      @cancel="resetUploadModal"
    >
      <template #title>
        <div class="kb-upload-title">
          <span class="kb-upload-title-mark">
            <a-icon type="cloud-upload" />
          </span>
          <div class="kb-upload-title-copy">
            <strong>上传文件</strong>
            <span>选择文件并设置解析策略</span>
          </div>
        </div>
      </template>
      <div class="kb-upload-modal">
        <div class="kb-upload-grid">
          <div class="kb-upload-inline-field kb-upload-directory-field">
            <span class="kb-upload-inline-label">上传目录：</span>
            <a-select
              v-model="selectedUploadParentId"
              size="large"
              class="kb-upload-inline-select kb-upload-folder-select"
              dropdown-class-name="kb-upload-folder-dropdown"
              option-label-prop="label"
            >
              <a-select-option :value="null" label="知识库根目录">
                <div class="kb-upload-folder-option is-root">
                  <span class="kb-upload-folder-option__icon">
                    <a-icon type="home" />
                  </span>
                  <span class="kb-upload-folder-option__content">
                    <span class="kb-upload-folder-option__name">知识库根目录</span>
                    <span class="kb-upload-folder-option__path">文件将直接放在知识库根目录</span>
                  </span>
                </div>
              </a-select-option>
              <a-select-option v-for="item in folderOptions" :key="item.id" :value="item.id" :label="item.name">
                <div class="kb-upload-folder-option" :style="{ paddingLeft: `${(item.level || 0) * 14}px` }">
                  <span class="kb-upload-folder-option__icon">
                    <a-icon :type="isFolderExpanded(item.id) ? 'folder-open' : 'folder'" />
                  </span>
                  <span class="kb-upload-folder-option__content">
                    <span class="kb-upload-folder-option__name">{{ item.name }}</span>
                    <span class="kb-upload-folder-option__path">{{ getFolderDepthLabel(item) }}</span>
                  </span>
                </div>
              </a-select-option>
            </a-select>
          </div>
          <div class="kb-upload-inline-field">
            <span class="kb-upload-inline-label">解析策略：</span>
            <a-select v-model="selectedParseStrategy" size="large" class="kb-upload-inline-select">
              <a-select-option v-for="item in parseStrategyOptions" :key="item.value" :value="item.value">
                {{ item.label }}
              </a-select-option>
            </a-select>
          </div>
          <div class="kb-upload-inline-field">
            <span class="kb-upload-inline-label">多模态解析：</span>
            <a-switch v-model="selectedMultimodalEnabled" size="default" />
            <span class="kb-upload-inline-hint">开启后图文文档（截图）会提取图片并识别内容</span>
          </div>
        </div>

        <a-upload-dragger
          :multiple="true"
          :before-upload="handleUploadBefore"
          :file-list="uploadDraftList"
          :show-upload-list="false"
          accept=".pdf,.doc,.docx,.txt,.md,.xlsx,.xls,.ppt,.pptx,.png,.jpg,.jpeg,.gif,.bmp,.webp,.svg"
          @remove="removeDraftFile"
        >
          <div class="kb-upload-dropzone">
            <div class="kb-upload-dropzone-icon">
              <a-icon type="inbox" />
            </div>
            <p class="kb-upload-dropzone-title">点击或拖拽文件到此区域，可一次选择多个文件</p>
            <p class="kb-upload-dropzone-hint">
              支持 PDF、Word、Markdown、Excel、PPT、图片。解析策略会统一应用到本次文件。
            </p>
          </div>
        </a-upload-dragger>

        <div v-if="uploadDraftList.length" class="kb-upload-selected">
          <div class="kb-upload-selected-head">
            <div class="kb-upload-selected-head-main">
              <span>待提交文件</span>
              <small>{{ uploadSubmitting ? uploadProgressText : "确认后统一入库并开始解析" }}</small>
            </div>
            <div class="kb-upload-selected-summary">
              <a-progress
                v-if="uploadSubmitting"
                type="circle"
                :percent="uploadOverallPercent"
                :width="36"
                :stroke-width="10"
              />
              <span class="kb-upload-selected-count">{{ uploadDraftList.length }} 个</span>
            </div>
          </div>
          <div class="kb-upload-selected-list">
            <div v-for="item in uploadDraftList" :key="item.uid" class="kb-upload-selected-item">
              <div class="kb-upload-selected-meta">
                <span class="kb-upload-selected-file-icon">
                  <a-icon type="file" />
                </span>
                <span class="kb-upload-selected-name">{{ item.name }}</span>
              </div>
              <div class="kb-upload-selected-actions">
                <div class="kb-upload-file-progress">
                  <span class="kb-upload-selected-size">{{ getUploadStatusText(item) }}</span>
                  <a-progress
                    v-if="uploadSubmitting || item.uploadPercent > 0"
                    :percent="item.uploadPercent || 0"
                    :status="getUploadProgressStatus(item)"
                    :show-info="false"
                    size="small"
                  />
                </div>
                <button
                  type="button"
                  class="kb-upload-remove-btn"
                  title="移除文件"
                  :disabled="uploadSubmitting"
                  @click="removeDraftFile(item)"
                >
                  <a-icon type="delete" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </a-modal>

    <a-modal
      v-model="showCreateFolderModal"
      :title="folderModalMode === 'rename' ? '重命名节点' : '新建文件夹'"
      :ok-text="folderModalMode === 'rename' ? '保存' : '创建'"
      cancel-text="取消"
      :confirm-loading="createFolderSubmitting"
      destroy-on-close
      @ok="submitCreateFolder"
      @cancel="resetCreateFolderModal"
    >
      <a-input
        v-model="createFolderForm.name"
        :placeholder="folderModalMode === 'rename' ? '请输入新的名称' : '请输入文件夹名称'"
        :max-length="64"
        allow-clear
        @pressEnter="submitCreateFolder"
      />
    </a-modal>

    <div
      v-if="contextMenu.visible"
      class="kd-tree-context-menu"
      :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"
      @click.stop
    >
      <a-menu @click="handleContextMenuClick">
        <a-menu-item v-if="canManageFiles && contextMenu.node?.isFolder" key="upload">上传到此目录</a-menu-item>
        <a-menu-item v-if="canManageFiles && contextMenu.node?.isFolder" key="create-child">新建子目录</a-menu-item>
        <a-menu-item v-if="canManageFiles && contextMenu.node?.isFolder" key="reparse-all">重新解析此目录</a-menu-item>
        <a-menu-item v-if="canManageFiles" key="rename">重命名</a-menu-item>
        <a-menu-item v-if="!contextMenu.node?.isFolder" key="download">下载</a-menu-item>
        <a-menu-item v-if="canManageFiles && !contextMenu.node?.isFolder" key="reparse">重新解析</a-menu-item>
        <a-menu-item v-if="canManageFiles" key="delete">
          <span class="text-red-500">删除</span>
        </a-menu-item>
      </a-menu>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  getKnowledgeBaseDetail,
  getFileTree,
  batchCreateKbFiles,
  createFolder,
  updateFileNode,
  moveFileNode,
  deleteFile,
  reparseFile,
  reparseAll,
  reparseAllByFolder,
  reindexFile,
  reindexKb,
  getParseStrategyConfigs,
  getKbMembers,
  getQaPairList
} from "@/api/knowledge"
import { downLoadByFileId, uploadFile as uploadCommonFile } from "@/api/common"
import { useUserStoreWithOut } from "@/store/modules/user"
import FilePreview from "@/components/file-preview/index.vue"
import { getKnowledgeTypeIcon } from "./constants"
import DocumentKnowledgePanel from "./components/document-knowledge-panel.vue"
import QaList from "./components/qa-list.vue"
import AuditManage from "./components/audit-manage.vue"
import MemberManage from "./components/member-manage.vue"
import OperationLog from "./components/operation-log.vue"
import RetrievalTest from "./components/retrieval-test.vue"
import KbSettingsForm from "./components/kb-settings-form.vue"
import KbStrategySettingsForm from "./components/kb-strategy-settings-form.vue"
import KnowledgeChatPanel from "./components/knowledge-chat-panel.vue"
import KbKnowledgeGraphPanel from "./components/kb-knowledge-graph-panel.vue"

const props = defineProps<{ kbId: string | number }>()

const route = useRoute()
const userStore = useUserStoreWithOut()
const currentKbId = computed(() => String(props.kbId || route.params.kbId))

const kbInfo = ref<any>(null)
const currentUserInfo = ref<any>(null)
const kbMembers = ref<any[]>([])
const pendingQaCount = ref(0)
const stage = ref<"ask" | "qa-root" | "graph" | "file">("ask")
const fileTree = ref<any[]>([])
const fileSearchKeyword = ref("")
const fileRootExpanded = ref(true)
const expandedFolderIds = ref<Array<string | number>>([])
const sidebarWidth = ref(280)
const selectedFileId = ref<string | null>(null)
const selectedFile = ref<any>(null)
const selectedPreviewChunkId = ref<string | number | null>(null)
const selectedPreviewBlockIds = ref<string[]>([])
const selectedPreviewPage = ref<number | null>(null)
const showParsePanel = ref(false)
const knowledgePanelRef = ref<any>(null)
const documentOverview = ref({ chunkCount: 0, imageCount: 0, flowCount: 0, entityCount: 0, relationCount: 0 })
const draggingNodeId = ref<string | number | null>(null)
const dragOverFolderId = ref<string | number | null>(null)
const dragOverRoot = ref(false)
const contextMenu = reactive({
  visible: false,
  x: 0,
  y: 0,
  node: null as any
})
const showUploadModal = ref(false)
const uploadSubmitting = ref(false)
const selectedUploadParentId = ref<string | number | null>(null)
const selectedParseStrategy = ref("default")
const selectedMultimodalEnabled = ref(false)
const parseStrategies = ref<any[]>([])
const uploadDraftList = ref<any[]>([])
const showCreateFolderModal = ref(false)
const createFolderSubmitting = ref(false)
const folderModalMode = ref<"create" | "rename">("create")
const createFolderForm = reactive({
  name: "",
  parentId: null as string | number | null,
  nodeId: null as string | number | null
})

const parseStrategyOptions = computed(() => [
  { label: "使用知识库默认策略", value: "default" },
  ...parseStrategies.value.map((item) => ({ label: item.name, value: item.id }))
])
const currentUserId = computed(() => String(currentUserInfo.value?.userId || currentUserInfo.value?.sysUserId || ""))
const currentUserName = computed(() => String(currentUserInfo.value?.realName || currentUserInfo.value?.name || ""))
const currentUserDeptIds = computed(() => {
  const dept = currentUserInfo.value?.dept || {}
  return toIdSet([
    currentUserInfo.value?.deptId,
    dept.deptId,
    dept.id,
    ...(Array.isArray(dept.ancestors) ? dept.ancestors : String(dept.ancestors || "").split(","))
  ])
})
const currentUserRoleIds = computed(() => {
  const roles = Array.isArray(currentUserInfo.value?.roles) ? currentUserInfo.value.roles : []
  return toIdSet(roles.flatMap((role: any) => [role.id, role.roleId, role.code]))
})
const currentUserKbRole = computed(() => {
  const matchedRoles = kbMembers.value
    .filter((item) => {
      const targetId = String(item.targetId || "")
      if (item.ruleType === "user") {
        return targetId === currentUserId.value
      }
      if (item.ruleType === "dept") {
        return currentUserDeptIds.value.has(targetId)
      }
      if (item.ruleType === "role") {
        return currentUserRoleIds.value.has(targetId)
      }
      return false
    })
    .map((item) => item.grantRole)
    .filter(Boolean)

  if (kbInfo.value?.createName && currentUserName.value && kbInfo.value.createName === currentUserName.value) {
    matchedRoles.push("admin")
  }

  return getHighestKbRole(matchedRoles)
})

function toIdSet(values: any[]) {
  return new Set(values.map((value) => String(value || "").trim()).filter(Boolean))
}

function getHighestKbRole(roles: string[]) {
  const roleWeight: Record<string, number> = {
    readonly: 1,
    editor: 2,
    reviewer: 3,
    admin: 4
  }
  return roles.reduce((best, role) => (roleWeight[role] > (roleWeight[best] || 0) ? role : best), "")
}

const canManageSettings = computed(() => currentUserKbRole.value === "admin")
const canManageFiles = computed(() => ["admin", "editor", "reviewer"].includes(currentUserKbRole.value))
const canReviewContent = computed(() => ["admin", "reviewer"].includes(currentUserKbRole.value))
let sidebarResizeCleanup: (() => void) | null = null

const showSettings = ref(false)
const settingsTab = ref("qa")
const settingsTabs = [
  { key: "qa", label: "问答对管理", icon: "question-circle", desc: "维护标准问答" },
  { key: "search", label: "检索测试", icon: "search", desc: "验证召回效果" },
  { key: "audit", label: "审核管理", icon: "audit", desc: "查看审核记录" },
  { key: "members", label: "成员权限", icon: "team", desc: "配置访问范围" },
  { key: "settings", label: "知识库基础设置", icon: "setting", desc: "名称、分类、标签与内容审核" },
  { key: "strategy", label: "策略配置", icon: "api", desc: "解析、检索与模型" },
  { key: "log", label: "操作日志", icon: "profile", desc: "追踪治理动作" }
]

const folderOptions = computed(() => fileTree.value.filter((item) => item.isFolder))
const uploadOverallPercent = computed(() => {
  if (!uploadDraftList.value.length) {
    return 0
  }
  const total = uploadDraftList.value.reduce((sum, item) => sum + Number(item.uploadPercent || 0), 0)
  return Math.round(total / uploadDraftList.value.length)
})
const uploadProgressText = computed(() => {
  const finished = uploadDraftList.value.filter((item) => isUploadFinalStatus(item.uploadStatus)).length
  const uploading = uploadDraftList.value.find((item) => item.uploadStatus === "uploading")
  if (uploading) {
    return `正在上传 ${finished + 1}/${uploadDraftList.value.length}：${uploading.name}`
  }
  if (uploadDraftList.value.some((item) => item.uploadStatus === "uploaded")) {
    return "文件上传完成，正在提交入库信息"
  }
  if (finished === uploadDraftList.value.length && finished > 0) {
    return "本次上传处理完成"
  }
  return `准备上传 ${uploadDraftList.value.length} 个文件`
})
const visibleFileTree = computed(() => {
  const keyword = fileSearchKeyword.value.trim().toLocaleLowerCase()
  if (keyword) {
    const matched = fileTree.value.filter((item) => String(item.name || "").toLocaleLowerCase().includes(keyword))
    const visibleIds = new Set<string>()
    matched.forEach((item) => {
      visibleIds.add(String(item.id))
      ;(item.ancestorIds || []).forEach((id: string | number) => visibleIds.add(String(id)))
    })
    return fileTree.value.filter((item) => visibleIds.has(String(item.id)))
  }
  return fileTree.value.filter((item) =>
    (item.ancestorIds || []).every((id: string | number) => expandedFolderIds.value.includes(id))
  )
})

function resetDetailViewState() {
  stage.value = "ask"
  selectedFileId.value = null
  selectedFile.value = null
  selectedPreviewChunkId.value = null
  selectedPreviewBlockIds.value = []
  selectedPreviewPage.value = null
  showParsePanel.value = false
  showSettings.value = false
  fileRootExpanded.value = true
  closeContextMenu()
}

async function refreshDetailPage() {
  await Promise.allSettled([loadKbDetail(), loadCurrentUserAndMembers()])
  await loadFileTree()
  loadParseStrategies()
}

onMounted(() => {
  document.addEventListener("click", closeContextMenu)
  window.addEventListener("scroll", closeContextMenu, true)
})

onActivated(async () => {
  resetDetailViewState()
  await refreshDetailPage()
})

watch(currentKbId, async (nextId, prevId) => {
  if (!nextId || prevId === undefined || nextId === prevId) {
    return
  }
  resetDetailViewState()
  await refreshDetailPage()
})

onBeforeUnmount(() => {
  document.removeEventListener("click", closeContextMenu)
  window.removeEventListener("scroll", closeContextMenu, true)
  stopSidebarResize()
})

async function loadKbDetail() {
  try {
    const res = await getKnowledgeBaseDetail(currentKbId.value)
    kbInfo.value = res?.datas && !Array.isArray(res.datas) ? res.datas : null
  } catch (e) {
    message.error("获取知识库详情失败")
  }
}

async function loadCurrentUserAndMembers() {
  try {
    currentUserInfo.value = userStore.userInfo || (await userStore.getInfoAction())
  } catch (e) {
    currentUserInfo.value = null
  }
  try {
    const res = await getKbMembers(currentKbId.value)
    kbMembers.value = Array.isArray(res?.datas) ? res.datas : []
  } catch (e) {
    kbMembers.value = []
  }
}

async function loadFileTree() {
  try {
    const res = await getFileTree(currentKbId.value, {})
    const tree = Array.isArray(res?.datas) ? res.datas : []
    const flatTree = flattenTree(tree)
    fileTree.value = flatTree
    expandedFolderIds.value = collectFolderIds(tree)
    if (canReviewContent.value) {
      await loadPendingAuditIndicators()
    } else {
      pendingQaCount.value = 0
    }
  } catch (e) {
    console.error(e)
  }
}

async function loadPendingAuditIndicators() {
  try {
    const qaRes = await getQaPairList(currentKbId.value, { auditStatus: "pending", pageNo: 1, pageSize: 1 })
    pendingQaCount.value = Number(qaRes?.count || 0)
  } catch (e) {
    pendingQaCount.value = 0
  }
  if (selectedFileId.value) {
    selectedFile.value =
      fileTree.value.find((item) => String(item.id) === String(selectedFileId.value)) || selectedFile.value
  }
}

async function refreshAuditIndicators() {
  await loadFileTree()
}

/** Chunk 编辑后同步文件树审核态（列表内联展示待审 Chunk，无需切换面板） */
async function onChunkEdited() {
  await refreshAuditIndicators()
}

/**
 * 拉取解析策略配置，用于上传时临时覆盖知识库默认策略。
 */
async function loadParseStrategies() {
  try {
    const res = await getParseStrategyConfigs({ kbId: currentKbId.value, status: "active" })
    parseStrategies.value = Array.isArray(res?.datas) ? res.datas : []
  } catch (e) {
    console.error(e)
    parseStrategies.value = []
  }
}

/**
 * 将嵌套文件树拍平为可渲染列表，保留层级信息
 */
function flattenTree(
  nodes: any[],
  parentId: string | null = null,
  level = 0,
  ancestorIds: Array<string | number> = []
): any[] {
  const result: any[] = []
  for (const node of nodes) {
    const isFolder = node.isFolder ?? node.nodeType === "folder"
    const children = Array.isArray(node.children) ? node.children : []
    result.push({ ...node, parentId, level, ancestorIds, isFolder, hasChildren: children.length > 0 })
    if (node.children?.length) {
      result.push(...flattenTree(node.children, node.id, level + 1, [...ancestorIds, node.id]))
    }
  }
  return result
}

function collectFolderIds(nodes: any[]): Array<string | number> {
  const ids: Array<string | number> = []
  for (const node of nodes) {
    const isFolder = node.isFolder ?? node.nodeType === "folder"
    if (isFolder) {
      ids.push(node.id)
    }
    if (node.children?.length) {
      ids.push(...collectFolderIds(node.children))
    }
  }
  return ids
}

/**
 * 打开上传弹窗，可指定目标目录。
 */
function openUploadModal(parentId: string | number | null = null) {
  if (!canManageFiles.value) {
    message.warning("当前用户无文件管理权限")
    return
  }
  selectedUploadParentId.value = parentId
  if (!parseStrategies.value.length) {
    loadParseStrategies()
  }
  showUploadModal.value = true
}

function selectFile(item: any) {
  closeContextMenu()
  if (item.isFolder) {
    toggleFolder(item)
    return
  }
  selectedFileId.value = item.id
  selectedFile.value = item
  selectedPreviewChunkId.value = null
  selectedPreviewBlockIds.value = []
  selectedPreviewPage.value = null
  documentOverview.value = { chunkCount: 0, imageCount: 0, flowCount: 0, entityCount: 0, relationCount: 0 }
  stage.value = "file"
  showParsePanel.value = item.parseStatus === "parsed"
}

function backToKbOverview() {
  stage.value = "graph"
  selectedPreviewChunkId.value = null
  selectedPreviewBlockIds.value = []
  selectedPreviewPage.value = null
}

function onDocumentOverview(value: any) {
  documentOverview.value = { ...documentOverview.value, ...(value || {}) }
}

function openKnowledgeTab(tab: string) {
  showParsePanel.value = true
  nextTick(() => knowledgePanelRef.value?.openTab?.(tab))
}

function fileParseStatusText(status: string) {
  return { parsed: "已解析", parsing: "解析中", failed: "解析失败", none: "待解析" }[status] || "待解析"
}

function fileTreeStateText(item: any) {
  return [
    fileParseStatusText(item.parseStatus),
    shouldShowAuditStatus(item) ? auditLabel(item.auditStatus) : "",
    shouldShowIndexStatus(item) ? indexStatusLabel(item.indexStatus) : ""
  ].filter(Boolean).join(" · ")
}

function onSelectChunkForPreview(chunk: any) {
  selectedPreviewChunkId.value = chunk?.id || chunk?.chunkId || null
  selectedPreviewBlockIds.value = parseChunkBlockIds(chunk?.blockIds)
  selectedPreviewPage.value = parseChunkPage(chunk)
}

function parseChunkPage(chunk: any): number | null {
  const page = Number(chunk?.pageStart || chunk?.page_start)
  return Number.isFinite(page) && page > 0 ? page : null
}

function parseChunkBlockIds(blockIds: any): string[] {
  if (Array.isArray(blockIds)) {
    return blockIds.map((id) => String(id).trim()).filter(Boolean)
  }
  if (!blockIds) {
    return []
  }
  if (typeof blockIds === "string") {
    try {
      const parsed = JSON.parse(blockIds)
      if (Array.isArray(parsed)) {
        return parsed.map((id) => String(id).trim()).filter(Boolean)
      }
    } catch (e) {
      return blockIds
        .split(",")
        .map((id) => id.trim().replace(/^["']|["']$/g, ""))
        .filter(Boolean)
    }
  }
  return []
}

function isFolderExpanded(folderId: string | number) {
  return expandedFolderIds.value.includes(folderId)
}

function toggleFolder(item: any) {
  if (!item.isFolder) return
  if (isFolderExpanded(item.id)) {
    expandedFolderIds.value = expandedFolderIds.value.filter((id) => id !== item.id)
  } else {
    expandedFolderIds.value = [...expandedFolderIds.value, item.id]
  }
}

function treeIconType(item: any) {
  if (item.isFolder) {
    return isFolderExpanded(item.id) ? "folder-open" : "folder"
  }
  if (/\.pdf$/i.test(item.name)) return "file-pdf"
  if (/\.(png|jpg|jpeg|gif|svg|webp)$/i.test(item.name)) return "file-image"
  if (/\.(doc|docx)$/i.test(item.name)) return "file-word"
  if (/\.(xls|xlsx)$/i.test(item.name)) return "file-excel"
  return "file"
}

function startSidebarResize(event: MouseEvent) {
  stopSidebarResize()
  const startX = event.clientX
  const startWidth = sidebarWidth.value

  const onMove = (moveEvent: MouseEvent) => {
    const nextWidth = startWidth + moveEvent.clientX - startX
    sidebarWidth.value = Math.min(420, Math.max(240, nextWidth))
  }

  const onUp = () => {
    document.removeEventListener("mousemove", onMove)
    document.removeEventListener("mouseup", onUp)
    document.body.classList.remove("is-kd-sidebar-resizing")
    sidebarResizeCleanup = null
  }

  sidebarResizeCleanup = onUp
  document.body.classList.add("is-kd-sidebar-resizing")
  document.addEventListener("mousemove", onMove)
  document.addEventListener("mouseup", onUp)
}

function stopSidebarResize() {
  if (sidebarResizeCleanup) {
    sidebarResizeCleanup()
  } else {
    document.body.classList.remove("is-kd-sidebar-resizing")
  }
}

/**
 * 打开目录树右键菜单。
 */
function openContextMenu(item: any, event: MouseEvent) {
  if (!canManageFiles.value && item.isFolder) {
    return
  }
  contextMenu.node = item
  contextMenu.x = event.clientX
  contextMenu.y = event.clientY
  contextMenu.visible = true
}

function closeContextMenu() {
  contextMenu.visible = false
}

function handleTreeMenuClick(item: any, event: any) {
  runTreeMenuAction(item, event.key)
}

function handleContextMenuClick(event: any) {
  if (!contextMenu.node) return
  runTreeMenuAction(contextMenu.node, event.key)
  closeContextMenu()
}

function handleFileRootMenuClick(event: any) {
  if (!canManageFiles.value) return
  if (event.key === "upload") {
    openUploadModal(null)
  } else if (event.key === "create-folder") {
    onCreateFolder(null)
  } else if (event.key === "reparse-all") {
    onReparseAll()
  }else if (event.key === "reindex") {
    onReindex()
  }
}

/**
 * 统一处理三点菜单和右键菜单动作。
 */
function runTreeMenuAction(item: any, key: string) {
  if (["upload", "create-child", "rename", "reparse", "reparse-all", "reindex", "delete"].includes(key) && !canManageFiles.value) {
    message.warning("当前用户无文件管理权限")
    return
  }
  if (key === "upload") {
    openUploadModal(item.id)
  } else if (key === "create-child") {
    onCreateFolder(item.id)
  } else if (key === "rename") {
    onRenameFolder(item)
  } else if (key === "download") {
    onDownloadFile(item)
  } else if (key === "reparse") {
    onReparseFile(item)
  } else if (key === "delete") {
    onDeleteFileItem(item)
  }else if (key === "reparse-all") {
    onReparseAllByFolder(item)
  } else if (key === "reindex") {
    onReindexFile(item)
  }
}

/**
 * 开始拖拽文件树节点。
 */
function onNodeDragStart(item: any, event: DragEvent) {
  if (!canManageFiles.value) {
    event.preventDefault()
    return
  }
  draggingNodeId.value = item.id
  event.dataTransfer?.setData("text/plain", String(item.id))
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move"
  }
}

function onNodeDragEnd() {
  draggingNodeId.value = null
  dragOverFolderId.value = null
  dragOverRoot.value = false
}

function onNodeDragOver(item: any) {
  if (!canManageFiles.value) return
  if (!item.isFolder || item.id === draggingNodeId.value) return
  dragOverRoot.value = false
  dragOverFolderId.value = item.id
}

function onNodeDragLeave(item: any) {
  if (dragOverFolderId.value === item.id) {
    dragOverFolderId.value = null
  }
}

function onTreeRootDragOver() {
  if (!canManageFiles.value) return
  if (!draggingNodeId.value) return
  dragOverFolderId.value = null
  dragOverRoot.value = true
}

function onTreeRootDragLeave(event: DragEvent) {
  const current = event.currentTarget as HTMLElement
  const related = event.relatedTarget as Node | null
  if (!related || !current.contains(related)) {
    dragOverRoot.value = false
  }
}

async function onDropToNode(item: any) {
  if (!canManageFiles.value) {
    onNodeDragEnd()
    return
  }
  if (!item.isFolder || !draggingNodeId.value || item.id === draggingNodeId.value) {
    onNodeDragEnd()
    return
  }
  await moveDraggedNode(item.id)
}

async function onDropToRoot() {
  if (!canManageFiles.value) {
    onNodeDragEnd()
    return
  }
  if (!draggingNodeId.value) return
  await moveDraggedNode(null)
}

/**
 * 提交移动请求并刷新文件树。
 */
async function moveDraggedNode(parentId: string | number | null) {
  const sourceId = draggingNodeId.value
  if (!sourceId) return
  try {
    await moveFileNode(currentKbId.value, sourceId, { parentId })
    message.success("移动成功")
    if (selectedFileId.value === sourceId) {
      selectedFile.value = { ...selectedFile.value, parentId }
    }
    loadFileTree()
  } catch (e) {
    console.error(e)
    message.error("移动失败")
  } finally {
    onNodeDragEnd()
  }
}

function fileIcon(name: string): string {
  if (/\.pdf$/i.test(name)) return "📄"
  if (/\.(doc|docx)$/i.test(name)) return "📝"
  if (/\.(xls|xlsx)$/i.test(name)) return "📊"
  if (/\.(png|jpg|jpeg|gif|svg)$/i.test(name)) return "🖼"
  return "📄"
}

function badgeClass(status: string) {
  const map: Record<string, string> = {
    approved: "kb-badge--ok",
    pending: "kb-badge--pending",
    rejected: "kb-badge--reject",
    partially_approved: "kb-badge--partial"
  }
  return map[status] || ""
}

function auditLabel(status: string) {
  const map: Record<string, string> = {
    approved: "已通过",
    pending: "待审核",
    rejected: "已拒绝",
    partially_approved: "部分通过"
  }
  return map[status] || status
}

function shouldShowAuditStatus(item: any) {
  if (!canReviewContent.value || !item?.auditStatus) {
    return false
  }
  // 仅解析成功后才展示审核态；解析中/失败/未解析时不展示，避免与解析态 chip 并存误导
  return item.parseStatus === "parsed"
}

function parseStatusBadgeClass(status: string) {
  const map: Record<string, string> = {
    parsed: "kb-badge--ok",
    parsing: "kb-badge--pending",
    failed: "kb-badge--reject"
  }
  return map[status] || ""
}

function parseStatusLabel(status: string) {
  const map: Record<string, string> = {
    parsed: "已解析",
    parsing: "解析中",
    failed: "解析失败"
  }
  return map[status] || ""
}
function shouldShowIndexStatus(item: any) {
  // 解析成功后才展示索引状态
  return !item.isFolder && item.parseStatus === "parsed" && item.indexStatus && item.indexStatus !== "none"
}

function indexStatusBadgeClass(status: string) {
  const map: Record<string, string> = {
    synced: "kb-badge--ok",
    indexing: "kb-badge--pending",
    failed: "kb-badge--reject"
  }
  return map[status] || ""
}

function indexStatusLabel(status: string) {
  const map: Record<string, string> = {
    synced: "已索引",
    indexing: "索引中",
    failed: "索引失败"
  }
  return map[status] || ""
}
/**
 * 选择上传文件后，仅暂存到弹框列表，不直接入库。
 */
function handleUploadBefore(file: File) {
  const exists = uploadDraftList.value.some(
    (item) => item.name === file.name && item.size === file.size && item.lastModified === file.lastModified
  )
  if (!exists) {
    uploadDraftList.value = [
      ...uploadDraftList.value,
      {
        uid: file.uid || `${file.name}-${file.size}-${file.lastModified}`,
        name: file.name,
        size: file.size,
        status: "done",
        uploadStatus: "waiting",
        uploadPercent: 0,
        uploadMessage: "",
        fileId: "",
        fileHash: "",
        type: file.type,
        lastModified: file.lastModified,
        raw: file
      }
    ]
  }
  return false
}

/**
 * 移除待上传文件。
 */
function removeDraftFile(file: any) {
  if (uploadSubmitting.value) {
    return false
  }
  uploadDraftList.value = uploadDraftList.value.filter((item) => item.uid !== file.uid)
  return true
}

/**
 * 重置上传弹框状态。
 */
function resetUploadModal() {
  showUploadModal.value = false
  uploadSubmitting.value = false
  selectedUploadParentId.value = null
  selectedParseStrategy.value = "default"
  selectedMultimodalEnabled.value = false
  uploadDraftList.value = []
}

/**
 * 将浏览器 File 转成知识库批量入库接口需要的文件元数据。
 */
function buildBatchFilePayload(file: File, uploadResult: any, fileHash: string) {
  const extension = file.name.includes(".") ? file.name.split(".").pop() || "" : ""
  return {
    fileId: String(uploadResult.id),
    fileName: file.name,
    originalName: file.name,
    fileSize: file.size,
    mimeType: file.type || "",
    fileExt: extension,
    fileHash,
    multimodalEnabled: selectedMultimodalEnabled.value
  }
}

function bytesToHex(bytes: Uint8Array) {
  return Array.from(bytes)
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("")
}

function rightRotate(value: number, bits: number) {
  return (value >>> bits) | (value << (32 - bits))
}

function calculateSha256Fallback(buffer: ArrayBuffer): string {
  const input = new Uint8Array(buffer)
  const bitLength = input.length * 8
  const paddedLength = Math.ceil((input.length + 9) / 64) * 64
  const padded = new Uint8Array(paddedLength)
  const words = new Uint32Array(paddedLength / 4)
  const hash = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
  ])
  const constants = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98,
    0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8,
    0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819,
    0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
    0xc67178f2
  ])
  const schedule = new Uint32Array(64)

  padded.set(input)
  padded[input.length] = 0x80
  const view = new DataView(padded.buffer)
  view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x100000000), false)
  view.setUint32(paddedLength - 4, bitLength >>> 0, false)

  for (let i = 0; i < words.length; i += 1) {
    words[i] = view.getUint32(i * 4, false)
  }

  for (let offset = 0; offset < words.length; offset += 16) {
    schedule.set(words.subarray(offset, offset + 16))
    for (let i = 16; i < 64; i += 1) {
      const s0 = rightRotate(schedule[i - 15], 7) ^ rightRotate(schedule[i - 15], 18) ^ (schedule[i - 15] >>> 3)
      const s1 = rightRotate(schedule[i - 2], 17) ^ rightRotate(schedule[i - 2], 19) ^ (schedule[i - 2] >>> 10)
      schedule[i] = (schedule[i - 16] + s0 + schedule[i - 7] + s1) >>> 0
    }

    let a = hash[0]
    let b = hash[1]
    let c = hash[2]
    let d = hash[3]
    let e = hash[4]
    let f = hash[5]
    let g = hash[6]
    let h = hash[7]

    for (let i = 0; i < 64; i += 1) {
      const s1 = rightRotate(e, 6) ^ rightRotate(e, 11) ^ rightRotate(e, 25)
      const ch = (e & f) ^ (~e & g)
      const temp1 = (h + s1 + ch + constants[i] + schedule[i]) >>> 0
      const s0 = rightRotate(a, 2) ^ rightRotate(a, 13) ^ rightRotate(a, 22)
      const maj = (a & b) ^ (a & c) ^ (b & c)
      const temp2 = (s0 + maj) >>> 0

      h = g
      g = f
      f = e
      e = (d + temp1) >>> 0
      d = c
      c = b
      b = a
      a = (temp1 + temp2) >>> 0
    }

    hash[0] = (hash[0] + a) >>> 0
    hash[1] = (hash[1] + b) >>> 0
    hash[2] = (hash[2] + c) >>> 0
    hash[3] = (hash[3] + d) >>> 0
    hash[4] = (hash[4] + e) >>> 0
    hash[5] = (hash[5] + f) >>> 0
    hash[6] = (hash[6] + g) >>> 0
    hash[7] = (hash[7] + h) >>> 0
  }

  const output = new Uint8Array(32)
  const outputView = new DataView(output.buffer)
  hash.forEach((value, index) => outputView.setUint32(index * 4, value, false))
  return bytesToHex(output)
}

async function calculateFileSha256(file: File): Promise<string> {
  const buffer = await file.arrayBuffer()
  if (window.crypto?.subtle) {
    const digest = await window.crypto.subtle.digest("SHA-256", buffer)
    return bytesToHex(new Uint8Array(digest))
  }
  return calculateSha256Fallback(buffer)
}

function assertKbApiSuccess(response: any, fallbackMessage: string) {
  if (
    response &&
    typeof response === "object" &&
    response.resp_code !== undefined &&
    Number(response.resp_code) !== 0
  ) {
    throw new Error(response.resp_msg || fallbackMessage)
  }
}

function getUploadErrorMessage(error: any) {
  const data = error?.response?.data
  return data?.resp_msg || data?.message || error?.message || "批量上传失败"
}

function getActionErrorMessage(error: any, fallbackMessage: string) {
  const data = error?.response?.data
  return data?.resp_msg || data?.message || error?.message || fallbackMessage
}

function normalizeBatchFileResults(response: any) {
  const results = Array.isArray(response?.datas) ? response.datas : Array.isArray(response) ? response : []
  return results.map((item: any) => ({
    fileId: String(item.fileId || ""),
    fileHash: String(item.fileHash || "").toLowerCase(),
    status: String(item.status || "").toUpperCase(),
    message: item.message || ""
  }))
}

function applyBatchFileResults(results: any[]) {
  const byFileId = new Map(results.filter((item) => item.fileId).map((item) => [item.fileId, item]))
  const byFileHash = new Map(results.filter((item) => item.fileHash).map((item) => [item.fileHash, item]))

  uploadDraftList.value.forEach((item) => {
    if (item.uploadStatus !== "uploaded") {
      return
    }
    const result = byFileId.get(String(item.fileId || "")) || byFileHash.get(String(item.fileHash || "").toLowerCase())
    if (!result) {
      item.uploadStatus = "error"
      item.uploadMessage = "入库结果缺失"
      return
    }
    if (result.status === "SUCCESS") {
      item.uploadStatus = "success"
      item.uploadMessage = result.message || "上传成功"
      return
    }
    if (result.status === "DUPLICATE") {
      item.uploadStatus = "duplicate"
      item.uploadMessage = result.message || "文件已存在，已跳过"
      return
    }
    item.uploadStatus = "error"
    item.uploadMessage = result.message || "上传失败"
  })
}

function collectUploadResultStats() {
  return uploadDraftList.value.reduce(
    (stats, item) => {
      if (item.uploadStatus === "success") stats.success += 1
      else if (item.uploadStatus === "duplicate") stats.duplicate += 1
      else if (item.uploadStatus === "error") stats.failed += 1
      return stats
    },
    { success: 0, duplicate: 0, failed: 0, total: uploadDraftList.value.length }
  )
}

function getUploadSummaryText(stats: { success: number; duplicate: number; failed: number; total: number }) {
  if (stats.success === stats.total) {
    return "全部文件上传成功"
  }
  if (stats.duplicate === stats.total) {
    return stats.total === 1 ? "文件已存在，已跳过" : "全部文件已存在，未重复入库"
  }
  if (stats.failed === stats.total) {
    return "文件上传失败，请查看失败原因"
  }
  if (stats.success > 0 && stats.duplicate > 0 && stats.failed === 0) {
    return `上传完成：成功 ${stats.success} 个，重复 ${stats.duplicate} 个，已自动跳过重复文件`
  }
  if (stats.success > 0 && stats.failed > 0 && stats.duplicate === 0) {
    return `上传完成：成功 ${stats.success} 个，失败 ${stats.failed} 个，请查看文件列表`
  }
  return `上传完成：成功 ${stats.success} 个，重复 ${stats.duplicate} 个，失败 ${stats.failed} 个，请查看文件列表`
}

function showUploadSummaryMessage() {
  const stats = collectUploadResultStats()
  const summary = getUploadSummaryText(stats)
  if (stats.failed > 0) {
    message.warning(summary)
  } else if (stats.success === 0 && stats.duplicate > 0) {
    message.info(summary)
  } else {
    message.success(summary)
  }
}

function isUploadFinalStatus(status: string) {
  return ["success", "duplicate", "error"].includes(status)
}

function getUploadProgressStatus(item: any) {
  if (item.uploadStatus === "error") {
    return "exception"
  }
  if (["success", "duplicate"].includes(item.uploadStatus)) {
    return "success"
  }
  return undefined
}

/**
 * 批量上传文件并统一写入知识库。
 */
async function submitUploadBatch() {
  if (!uploadDraftList.value.length) {
    message.warning("请先选择文件")
    return
  }

  uploadSubmitting.value = true
  try {
    uploadDraftList.value.forEach((item) => {
      item.uploadStatus = "waiting"
      item.uploadPercent = 0
      item.uploadMessage = ""
      item.fileId = ""
      item.fileHash = ""
    })
    const uploadedFiles = []
    for (const item of uploadDraftList.value) {
      try {
        item.uploadStatus = "uploading"
        item.uploadPercent = 1
        const fileHash = await calculateFileSha256(item.raw)
        const result = await uploadCommonFile(item.raw, {
          onUploadProgress: (event: ProgressEvent) => {
            if (!event.total) {
              return
            }
            item.uploadPercent = Math.min(95, Math.round((event.loaded / event.total) * 100))
          }
        })
        if (!result?.id) {
          throw new Error("通用上传未返回 fileId")
        }
        item.uploadStatus = "uploaded"
        item.uploadPercent = 100
        item.fileId = String(result.id)
        item.fileHash = fileHash
        item.uploadMessage = "已上传，等待入库"
        uploadedFiles.push(buildBatchFilePayload(item.raw, result, fileHash))
      } catch (fileError) {
        item.uploadStatus = "error"
        item.uploadPercent = 100
        item.uploadMessage = getUploadErrorMessage(fileError)
      }
    }

    if (uploadedFiles.length) {
      try {
        const createResult = await batchCreateKbFiles(currentKbId.value, {
          parentId: selectedUploadParentId.value,
          parseStrategyConfigId: selectedParseStrategy.value === "default" ? null : selectedParseStrategy.value,
          files: uploadedFiles
        })
        assertKbApiSuccess(createResult, "批量上传失败")
        applyBatchFileResults(normalizeBatchFileResults(createResult))
      } catch (createError) {
        const errorMessage = getUploadErrorMessage(createError)
        uploadDraftList.value.forEach((item) => {
          if (item.uploadStatus === "uploaded" || item.uploadStatus === "uploading") {
            item.uploadStatus = "error"
            item.uploadMessage = errorMessage
          }
        })
      }
    }

    showUploadSummaryMessage()
    if (uploadDraftList.value.some((item) => item.uploadStatus === "success")) {
      loadFileTree()
    }
  } catch (e) {
    console.error(e)
    uploadDraftList.value.forEach((item) => {
      if (item.uploadStatus === "uploading" || item.uploadStatus === "uploaded") {
        item.uploadStatus = "error"
        item.uploadMessage = getUploadErrorMessage(e)
      }
    })
    message.error(getUploadErrorMessage(e))
  } finally {
    uploadSubmitting.value = false
  }
}

function getFolderDepthLabel(item: any) {
  const level = Number(item.level || 0)
  return level > 0 ? `第 ${level + 1} 级目录` : "一级目录"
}

async function onDeleteFileItem(item: any) {
  try {
    await deleteFile(currentKbId.value, item.id)
    message.success("删除成功")
    if (selectedFileId.value === item.id) {
      selectedFile.value = null
      selectedFileId.value = null
      stage.value = "ask"
    }
    loadFileTree()
  } catch (e) {
    message.error("删除失败")
  }
}

async function onReparseFile(item: any) {
  try {
    await reparseFile(currentKbId.value, item.id)
    message.success("重新解析已触发")
    loadFileTree()
  } catch (e) {
    message.error(getActionErrorMessage(e, "触发重新解析失败"))
  }
}

async function onDownloadFile(item: any) {
  const fileId = item?.fileId
  if (!fileId) {
    message.warning("当前文件缺少下载ID")
    return
  }

  try {
    const res = await downLoadByFileId(fileId)
    const blob = res.data instanceof Blob ? res.data : new Blob([res.data])
    if (blob.type === "application/json") {
      const data = JSON.parse(await blob.text())
      message.warning(data?.msg || data?.resp_msg || "下载失败")
      return
    }

    const url = window.URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = getDownloadFileName(
      res.headers?.["content-disposition"],
      item.name || item.originalName || "download"
    )
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch (e) {
    console.error(e)
    message.error("下载失败")
  }
}

function getDownloadFileName(contentDisposition: string | undefined, fallbackName: string) {
  if (!contentDisposition) {
    return fallbackName
  }

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  const plainMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
  const fileName = utf8Match?.[1] || plainMatch?.[1]
  if (!fileName) {
    return fallbackName
  }

  try {
    return decodeURIComponent(fileName)
  } catch (e) {
    return fileName
  }
}

/**
 * 打开新建文件夹弹窗，默认在当前知识库根目录创建。
 */
function onCreateFolder(parentId: string | number | null = null) {
  if (!canManageFiles.value) {
    message.warning("当前用户无文件管理权限")
    return
  }
  folderModalMode.value = "create"
  createFolderForm.parentId = parentId
  createFolderForm.nodeId = null
  createFolderForm.name = ""
  showCreateFolderModal.value = true
}

function onRenameFolder(item: any) {
  if (!canManageFiles.value) {
    message.warning("当前用户无文件管理权限")
    return
  }
  folderModalMode.value = "rename"
  createFolderForm.parentId = item.parentId ?? null
  createFolderForm.nodeId = item.id
  createFolderForm.name = item.name || ""
  showCreateFolderModal.value = true
}

async function onReparseAll() {
  Modal.confirm({
    title: "确认重新解析全部？",
    content: "将触发当前知识库下所有文件的重新解析，已解析的数据将被新结果替换。",
    okType: "danger",
    okText: "开始解析",
    cancelText: "取消",
    async onOk() {
      try {
        const res = await reparseAll(currentKbId.value)
        message.success(res?.resp_msg || "已触发重新解析")
        loadFileTree()
      } catch (e) {
        message.error(getActionErrorMessage(e, "触发重新解析失败"))
      }
    }
  })
}

async function onReparseAllByFolder(item) {
  Modal.confirm({
    title: `确认重新解析「${item.name}」下全部文件？`,
    content: "将触发该目录（含子目录）下所有文件的重新解析。",
    okType: "danger",
    okText: "开始解析",
    cancelText: "取消",
    async onOk() {
      try {
        const res = await reparseAllByFolder(currentKbId.value, item.id)
        message.success(res?.resp_msg || "已触发重新解析")
        loadFileTree()
      } catch (e) {
        message.error(getActionErrorMessage(e, "触发重新解析失败"))
      }
    }
  })
}
async function onReindexFile(item: any) {
  try {
    await reindexFile(currentKbId.value, item.id)
    message.success("已触发重新索引")
    loadFileTree()
  } catch (e) {
    message.error(getActionErrorMessage(e, "触发重新索引失败"))
  }
}
async function onReindex() {
  Modal.confirm({
    title: "确认重新索引？",
    content: "将跳过解析，直接使用已解析的 chunks 重建索引。适用于索引丢失或索引配置变更的场景。",
    okText: "开始索引",
    cancelText: "取消",
    async onOk() {
      try {
        const res = await reindexKb(currentKbId.value)
        message.success(res?.resp_msg || "已触发重新索引")
        loadFileTree()
      } catch (e) {
        message.error(getActionErrorMessage(e, "触发重新索引失败"))
      }
    }
  })
}
/**
 * 提交新建文件夹或重命名节点请求并刷新左侧知识目录。
 */
async function submitCreateFolder() {
  const name = createFolderForm.name.trim()
  if (!name) {
    message.warning("请输入文件夹名称")
    return
  }

  createFolderSubmitting.value = true
  try {
    if (folderModalMode.value === "rename") {
      if (!createFolderForm.nodeId) {
        message.warning("请选择要重命名的节点")
        return
      }
      await updateFileNode(currentKbId.value, createFolderForm.nodeId, { name })
      message.success("重命名成功")
    } else {
      await createFolder(currentKbId.value, {
        name,
        parentId: createFolderForm.parentId
      })
      message.success("文件夹创建成功")
      fileRootExpanded.value = true
    }
    resetCreateFolderModal()
    loadFileTree()
  } catch (e) {
    console.error(e)
    message.error(folderModalMode.value === "rename" ? "重命名失败" : "文件夹创建失败")
  } finally {
    createFolderSubmitting.value = false
  }
}

/**
 * 重置新建文件夹弹窗状态。
 */
function resetCreateFolderModal() {
  showCreateFolderModal.value = false
  folderModalMode.value = "create"
  createFolderForm.name = ""
  createFolderForm.parentId = null
  createFolderForm.nodeId = null
}

/**
 * 格式化待上传文件大小。
 */
function formatUploadSize(size?: number) {
  if (!size) return "-"
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function getUploadStatusText(item: any) {
  if (item.uploadStatus === "uploading") {
    return `上传中 ${item.uploadPercent || 0}%`
  }
  if (item.uploadStatus === "uploaded") {
    return item.uploadMessage || "已上传，等待入库"
  }
  if (item.uploadStatus === "success") {
    return item.uploadMessage || "上传成功"
  }
  if (item.uploadStatus === "duplicate") {
    return item.uploadMessage || "已存在，已跳过"
  }
  if (item.uploadStatus === "error") {
    return item.uploadMessage || "上传失败"
  }
  return formatUploadSize(item.size)
}
</script>

<style lang="less" scoped>
@primary: #2563eb;
@primary-soft: #eff6ff;
@border: #e5e7eb;
@muted: #64748b;

/* ---- V2 主布局 ---- */
.kb-page-inner--full {
  max-width: calc(100vw - 32px);
}

.kb-detail-page {
  overflow: hidden;
  height: 100vh;
  min-height: 0;
  box-sizing: border-box;
}

.kb-detail-page .kb-page-inner--full {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
}

.kd-v2 {
  display: grid;
  overflow: hidden;
  flex: 1;
  min-height: 0;
  background: #fff;
  border: 1px solid @border;
  border-radius: 14px;
  transition: grid-template-columns 0.26s cubic-bezier(0.22, 1, 0.36, 1);
  grid-template-columns: var(--kd-sidebar-width, 280px) 8px minmax(0, 1fr);
}

/* ---- 左栏 ---- */
.kd-v2-sidebar {
  display: flex;
  overflow: hidden;
  padding: 12px 10px 10px;
  min-height: 0;
  background: linear-gradient(180deg, #fafbfc, #f8fafc);
  transition: opacity 0.2s ease, transform 0.24s ease, padding 0.24s ease, border-color 0.24s ease;
  flex-direction: column;
  border-right: 1px solid @border;
}

.kd-v2-resizer {
  position: relative;
  cursor: col-resize;
  background: linear-gradient(180deg, #f8fafc, #eef2f7);
  transition: opacity 0.18s ease, width 0.24s ease;

  &::after {
    position: absolute;
    top: 50%;
    left: 50%;
    width: 2px;
    height: 44px;
    background: #cbd5e1;
    border-radius: 999px;
    opacity: 0;
    transition: opacity 0.16s, background 0.16s;
    content: "";
    transform: translate(-50%, -50%);
  }

  &:hover::after {
    background: #60a5fa;
    opacity: 1;
  }
}

.kd-v2-sidebar-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 6px 10px;
  font-size: 14px;
  font-weight: 700;
  color: #334155;
}

.kd-v2-select {
  display: flex;
  align-items: center;
  padding: 8px 10px;
  margin-bottom: 10px;
  font-size: 13px;
  background: #fff;
  border: 1px solid @border;
  border-radius: 10px;
  gap: 8px;
}

.kd-v2-select-thumb {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  width: 28px;
  height: 28px;
  background: linear-gradient(145deg, #f0f7ff 0%, #e0edff 100%);
  border-radius: 8px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
  flex-shrink: 0;

  .anticon {
    font-size: 15px;
    color: @primary;
  }
}

.kd-v2-select-label {
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #0f172a;
  flex: 1;
}

.kd-v2-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.kd-v2-add {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 0 12px;
  height: 38px;
  font-size: 13px;
  font-weight: 600;
  color: #334155;
  background: #fff;
  border: 1px solid @border;
  border-radius: 10px;
  transition: all 0.12s;
  flex: 1;
  cursor: pointer;

  &:hover {
    color: @primary;
    border-color: #93c5fd;
  }
}

.kd-v2-ask-btn {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 0 12px;
  margin-bottom: 10px;
  width: 100%;
  height: 38px;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  background: #fff;
  border: 1px solid @border;
  border-radius: 10px;
  transition: all 0.12s;
  gap: 8px;
  cursor: pointer;

  &:hover {
    color: @primary;
    border-color: #93c5fd;
  }

  &.is-active {
    color: #1d4ed8;
    background: @primary-soft;
    border-color: #bfdbfe;
  }
}

/* ---- 目录树 ---- */
.kd-v2-tree-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 6px 8px;
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.kd-v2-tree-search {
  margin: 0 4px 8px;
  width: calc(100% - 8px);

  &::v-deep .ant-input {
    height: 30px;
    font-size: 12px;
    background: #fff;
    border-color: #e2e8f0;
    border-radius: 7px;
  }
}

.kd-v2-tree {
  display: flex;
  overflow: auto;
  padding-right: 4px;
  min-height: 120px;
  flex: 1;
  flex-direction: column;
  gap: 2px;

  &.is-drag-over-root {
    background: rgba(239, 246, 255, 0.6);
    outline: 1px dashed #93c5fd;
    outline-offset: 2px;
  }
}

.kd-tree-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.kd-tree-list--files {
  margin-top: 1px;
}

.kd-tree-row {
  display: flex;
  align-items: center;
  padding: 2px 5px 2px 6px;
  border: 1px solid transparent;
  border-radius: 8px;
  transition: background 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
  gap: 3px;
  cursor: pointer;

  &:hover {
    background: rgba(248, 250, 252, 0.92);
  }

  &.is-active {
    background: #eff6ff;
    border-color: rgba(147, 197, 253, 0.48);
    box-shadow: inset 2px 0 0 #3b82f6;
  }

  &.is-dragging {
    opacity: 0.45;
  }

  &.is-drag-over {
    background: #dbeafe;
    border-color: #60a5fa;
  }
}

.kd-tree-row--system {
  margin-top: 1px;
  background: transparent;

  .kd-tree-name {
    font-weight: 700;
    color: #334155;
  }

  &:hover {
    background: #f8fafc;
    box-shadow: none;
  }

  &.is-active {
    background: #f8fbff;
    border-color: rgba(191, 219, 254, 0.7);
  }
}

.kd-tree-label {
  display: flex;
  align-items: center;
  padding: 5px 4px;
  min-width: 0;
  font-size: 13px;
  color: #334155;
  gap: 6px;
  flex: 1;
}

.kd-tree-toggle {
  padding: 0;
  width: 16px;
  height: 16px;
  font-size: 10px;
  color: #94a3b8;
  background: transparent;
  border: none;
  transition: transform 0.18s ease, color 0.18s ease;
  cursor: pointer;

  &.is-open {
    color: #2563eb;
    transform: rotate(90deg);
  }
}

.kd-tree-toggle--placeholder {
  display: inline-block;
  flex-shrink: 0;
  cursor: default;
}

.kd-tree-icon {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  width: 18px;
  height: 18px;
  font-size: 14px;
  flex-shrink: 0;

  &.is-folder {
    color: #f6a21a;
  }

  &.is-file {
    color: #8a97a8;
  }

  &.is-system {
    color: #64748b;
  }

  &.is-file-root {
    color: #f6a21a;
  }

  &.is-graph-root {
    color: #2563eb;
  }
}

.kd-tree-scope {
  padding: 1px 6px;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.05em;
  color: #1d4ed8;
  background: #dbeafe;
  border-radius: 99px;
}

.kd-tree-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kd-tree-file-state {
  width: 7px;
  height: 7px;
  background: #cbd5e1;
  border-radius: 50%;
  flex-shrink: 0;

  &.is-parsed { background: #22c55e; }
  &.is-parsing { background: #3b82f6; }
  &.is-failed { background: #ef4444; }
}

.kd-tree-lock {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  width: 24px;
  height: 24px;
  font-size: 12px;
  color: #cbd5e1;
  flex-shrink: 0;

  .kd-tree-row:hover & {
    color: #94a3b8;
  }
}

.kd-tree-root-add {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  width: 24px;
  height: 24px;
  color: #2563eb;
  background: transparent;
  border: none;
  border-radius: 7px;
  transition: background 0.16s ease, color 0.16s ease;
  flex-shrink: 0;
  cursor: pointer;

  &:hover {
    color: #1d4ed8;
    background: #eff6ff;
  }
}

.kd-tree-pending-dot {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  padding: 0 5px;
  min-width: 18px;
  height: 18px;
  font-size: 11px;
  font-weight: 700;
  color: #b45309;
  background: #fef3c7;
  border: 1px solid #fde68a;
  border-radius: 999px;
}

.kd-tree-status-badge {
  padding: 1px 5px;
  max-width: 58px;
  font-size: 10px;
  white-space: nowrap;
  line-height: 16px;
  flex-shrink: 0;
}

.kd-tree-empty {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 18px 12px 16px;
  font-size: 12px;
  text-align: center;
  color: #94a3b8;
  flex-direction: column;
  gap: 6px;
}

.kd-tree-empty__text {
  color: #94a3b8;
}

.kd-tree-empty__actions {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  color: #cbd5e1;
  gap: 6px;

  button {
    padding: 0;
    font-size: 12px;
    color: @primary;
    background: transparent;
    border: none;
    cursor: pointer;

    &:hover {
      text-decoration: underline;
      color: #1d4ed8;
    }
  }
}

.kd-tree-more {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 28px;
  height: 28px;
  font-size: 16px;
  color: @muted;
  border-radius: 8px;
  cursor: pointer;
  flex-shrink: 0;

  &:hover {
    color: #0f172a;
    background: #e2e8f0;
  }
}

.kd-tree-list-enter-active,
.kd-tree-list-leave-active {
  transition: opacity 0.16s ease, transform 0.16s ease, max-height 0.18s ease;
}

.kd-tree-list-enter,
.kd-tree-list-leave-to {
  max-height: 0;
  opacity: 0;
  transform: translateY(-4px);
}

.kd-tree-list-enter-to,
.kd-tree-list-leave {
  max-height: 40px;
  opacity: 1;
  transform: translateY(0);
}

.kd-tree-context-menu {
  position: fixed;
  z-index: 3000;
  overflow: hidden;
  min-width: 132px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.14);
}

/* ---- 底部按钮 ---- */
.kd-v2-sidebar-foot {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  padding-top: 12px;
  margin-top: auto;
  border-top: 1px solid #e2e8f0;
}

.kd-v2-foot-btn {
  padding: 8px 10px;
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  background: #fff;
  border: 1px solid @border;
  border-radius: 10px;
  transition: all 0.12s;
  cursor: pointer;

  &:hover:not(:disabled) {
    color: #1d4ed8;
    border-color: #93c5fd;
  }

  &:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
}

/* ---- 右侧主区 ---- */
.kd-v2-main {
  display: flex;
  min-width: 0;
  min-height: 0;
  background: #fff;
  flex-direction: column;
}

.kd-v2-stage {
  display: flex;
  overflow: auto;
  min-height: 0;
  flex: 1;
  flex-direction: column;
}

.kd-v2-stage-inner {
  padding: 20px 24px 28px;
  flex: 1;
  min-height: 0;
}

.kd-v2-stage-inner--chat {
  display: flex;
  padding: 0;
  min-height: 0;
}

.kd-v2-stage--chat {
  overflow: hidden;
}

.kd-v2-stage--qa {
  overflow: hidden;
}

.kd-v2-stage--graph {
  overflow: hidden;
}

.kd-v2-qa-list {
  min-height: 0;
  flex: 1;
}

.kd-v2-file-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-start;
  padding: 11px 20px;
  gap: 12px;
  border-bottom: 1px solid @border;
  flex-shrink: 0;
}

.kd-v2-file-title-wrap {
  display: flex;
  align-items: flex-start;
  min-width: 0;
  gap: 10px;
}

.kd-v2-file-title-main {
  min-width: 0;
}

.kd-v2-file-title-line {
  display: flex;
  align-items: center;
  gap: 9px;
}

.kd-v2-file-back {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  width: 32px;
  height: 32px;
  color: #2563eb;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.14s ease;

  &:hover {
    color: #fff;
    background: #2563eb;
    border-color: #2563eb;
  }
}

.kd-v2-file-title {
  margin: 0 0 3px;
  font-size: 17px;
  font-weight: 700;
}

.kd-v2-file-status {
  padding: 2px 8px;
  font-size: 11px;
  color: #64748b;
  background: #f1f5f9;
  border-radius: 99px;

  &.is-parsed { color: #15803d; background: #dcfce7; }
  &.is-parsing { color: #1d4ed8; background: #dbeafe; }
  &.is-failed { color: #b91c1c; background: #fee2e2; }
}

.kd-v2-file-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 0;

  button {
    padding: 3px 8px;
    font-size: 11px;
    color: #64748b;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    cursor: pointer;

    &:hover { color: #1d4ed8; border-color: #93c5fd; }
    strong { color: #1e293b; }
  }
}

.kd-v2-file-subline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px 10px;
}

.kd-v2-file-meta {
  margin: 0;
  font-size: 13px;
  color: @muted;
}

.kd-v2-file-error {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: #dc2626;
}

.kd-v2-preview {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 20px;
  min-height: 280px;
  background: linear-gradient(180deg, #f8fafc, #fff);
  flex: 1;
}

.kd-v2-file-workspace {
  display: grid;
  overflow: hidden;
  min-height: 0;
  background: linear-gradient(180deg, #f8fafc, #fff);
  transition: grid-template-columns 0.28s cubic-bezier(0.22, 1, 0.36, 1);
  grid-template-columns: minmax(0, 1fr);
  flex: 1;

  &.is-parse-mode {
    grid-template-columns: minmax(420px, 1fr) minmax(340px, 39%);
  }

  .kd-v2-preview {
    overflow: auto;
    min-height: 0;
    background: transparent;
    transition: padding 0.22s ease;
  }
}

.kd-v2-preview-file {
  width: 100%;
  height: 100%;
  min-height: 0;
}

.kd-v2-preview-file::v-deep .iframe-wrapper {
  justify-content: stretch;
  align-items: stretch;
  padding: 0;
  width: 100%;
}

.kd-v2-preview-file::v-deep .preview-iframe {
  width: 100%;
}

.kd-v2-preview-placeholder {
  padding: 48px 32px;
  max-width: 420px;
  text-align: center;
  color: @muted;
  background: #fff;
  border: 1px dashed #cbd5e1;
  border-radius: 16px;

  p {
    margin: 0 0 8px;
    font-weight: 600;
    color: #475569;
  }
}

.kd-parse-panel {
  overflow: hidden;
  padding: 0;
  min-width: 0;
  background: #fafbfc;
  box-shadow: -16px 0 30px rgba(15, 23, 42, 0.06);
  border-left: 1px solid @border;
}

.kd-parse-slide-enter-active,
.kd-parse-slide-leave-active {
  transition: opacity 0.22s ease, transform 0.26s cubic-bezier(0.22, 1, 0.36, 1);
}

.kd-parse-slide-enter,
.kd-parse-slide-leave-to {
  opacity: 0;
  transform: translateX(24px);
}

.kd-parse-slide-enter-to,
.kd-parse-slide-leave {
  opacity: 1;
  transform: translateX(0);
}

/* ---- Ask Composer（复用 ask-ai 样式） ---- */
.ask-composer {
  padding: 18px;
  background: #fff;
  border: 1px solid @border;
  border-radius: 16px;
  box-shadow: 0 4px 24px rgba(15, 23, 42, 0.06);
}

.ask-mode-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.ask-pill {
  padding: 6px 14px;
  font-size: 13px;
  color: #475569;
  background: #fff;
  border: 1px solid @border;
  border-radius: 999px;
  cursor: pointer;

  &.is-on {
    font-weight: 600;
    color: #1d4ed8;
    background: @primary-soft;
    border-color: @primary;
  }
}

.kd-scope-pill {
  padding: 6px 12px;
  margin-left: auto;
  font-size: 13px;
  white-space: nowrap;
  color: @muted;
  background: #f8fafc;
  border: 1px solid @border;
  border-radius: 10px;
}

.ask-input {
  padding: 14px !important;
  font-size: 15px !important;
  border-radius: 12px !important;
}

.ask-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}

.ask-hint {
  font-size: 12px;
  color: #94a3b8;
}

.ask-btn-send {
  padding: 10px 24px;
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  background: @primary;
  border: none;
  border-radius: 999px;
  cursor: pointer;

  &:hover {
    background: #1d4ed8;
  }
}

/* ---- 设置全屏工作台 ---- */
.kd-drawer {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  padding: 16px;
  background: rgba(15, 23, 42, 0.42);
  animation: kd-fade-in 0.15s ease;
}

@keyframes kd-fade-in {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}

.kd-drawer-panel {
  position: relative;
  display: flex;
  overflow: hidden;
  width: 100%;
  height: 100%;
  background: #fff;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 18px;
  box-shadow: 0 24px 70px rgba(15, 23, 42, 0.24);
  flex-direction: column;
  animation: kd-settings-zoom-in 0.18s ease-out;
}

@keyframes kd-settings-zoom-in {
  from {
    transform: translateY(12px) scale(0.985);
    opacity: 0.9;
  }

  to {
    transform: translateY(0) scale(1);
    opacity: 1;
  }
}

.kd-drawer-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 22px;
  border-bottom: 1px solid @border;
  flex-shrink: 0;
  background: linear-gradient(180deg, #fff, #f8fafc);

  h2 {
    margin: 0;
    font-size: 17px;
  }
}

.kd-drawer-close {
  width: 36px;
  height: 36px;
  font-size: 20px;
  color: @muted;
  background: #f1f5f9;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  line-height: 1;
}

.kd-drawer-body {
  flex: 1;
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  min-height: 0;
}

.kd-drawer-rail {
  display: flex;
  overflow: auto;
  padding: 12px 8px;
  background: #f8fafc;
  border-right: 1px solid @border;
  flex-direction: column;
  gap: 4px;

  button {
    display: flex;
    align-items: center;
    padding: 10px;
    width: 100%;
    font: inherit;
    text-align: left;
    color: #475569;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    gap: 10px;
    cursor: pointer;
    transition: background 0.18s ease, border-color 0.18s ease, transform 0.18s ease;

    &:hover {
      background: #fff;
      border-color: #dbeafe;
      transform: translateX(2px);
    }
  }

  .is-active {
    font-weight: 600;
    color: #1d4ed8;
    background: #fff;
    border-color: #bfdbfe;
  }
}

.kd-drawer-rail-icon {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  width: 32px;
  height: 32px;
  color: #2563eb;
  background: #eef6ff;
  border-radius: 10px;
  flex-shrink: 0;
}

.kd-drawer-rail-text {
  display: flex;
  flex-direction: column;
  min-width: 0;

  span {
    font-size: 13px;
    font-weight: 700;
    line-height: 1.25;
  }

  small {
    overflow: hidden;
    margin-top: 3px;
    font-size: 12px;
    font-weight: 400;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: #94a3b8;
  }
}

.kd-drawer-rail .is-active .kd-drawer-rail-icon {
  color: #fff;
  background: #2563eb;
}

.kd-drawer-stage {
  overflow: auto;
  padding: 22px 26px 30px;
  min-width: 0;
  background: #fff;
}

.kb-upload-modal {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.kb-upload-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.kb-upload-title-mark {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 36px;
  height: 36px;
  color: @primary;
  background: linear-gradient(135deg, #dbeafe, #eff6ff);
  border-radius: 12px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.kb-upload-title-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.kb-upload-title-copy strong {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.2;
}

.kb-upload-title-copy span {
  font-size: 12px;
  color: #64748b;
  line-height: 1.4;
}

.kb-upload-grid {
  display: flex;
  gap: 14px;
}

.kb-upload-inline-field {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.kb-upload-inline-label {
  font-size: 13px;
  font-weight: 700;
  color: #334155;
  flex: none;
  line-height: 1;
}

.kb-upload-directory-field {
  position: relative;
  flex-wrap: wrap;
}

.kb-upload-inline-select {
  flex: 1;
  min-width: 0;
}

.kb-upload-inline-select ::v-deep(.ant-select-selection) {
  height: 46px;
  border: 1px solid #dbe3ee;
  border-radius: 14px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.kb-upload-inline-select ::v-deep(.ant-select-selection__rendered) {
  margin-right: 30px;
  font-size: 15px;
  color: #0f172a;
  line-height: 44px;
}

.kb-upload-inline-select ::v-deep(.ant-select-selection-selected-value),
.kb-upload-inline-select ::v-deep(.ant-select-selection__placeholder) {
  font-size: 15px;
  line-height: 44px;
}

.kb-upload-inline-select ::v-deep(.ant-select-arrow) {
  color: #94a3b8;
}

.kb-upload-inline-select ::v-deep(.ant-select-focused .ant-select-selection),
.kb-upload-inline-select ::v-deep(.ant-select-selection:hover) {
  border-color: #93c5fd;
}

.kb-upload-folder-select ::v-deep(.ant-select-selection) {
  background: linear-gradient(#fff, #fff) padding-box,
    linear-gradient(135deg, rgba(37, 99, 235, 0.38), rgba(14, 165, 233, 0.2)) border-box;
}

::v-deep(.kb-upload-folder-dropdown) {
  padding: 8px;
  border-radius: 14px;
  box-shadow: 0 18px 46px rgba(15, 23, 42, 0.16);
}

::v-deep(.kb-upload-folder-dropdown .ant-select-dropdown-menu-item) {
  padding: 4px;
  border-radius: 10px;
}

::v-deep(.kb-upload-folder-dropdown .ant-select-dropdown-menu-item:hover),
::v-deep(.kb-upload-folder-dropdown .ant-select-dropdown-menu-item-active) {
  background: #f1f7ff;
}

::v-deep(.kb-upload-folder-dropdown .ant-select-dropdown-menu-item-selected) {
  font-weight: 600;
  color: #1d4ed8;
  background: #eaf2ff;
}

.kb-upload-folder-option {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 42px;
}

.kb-upload-folder-option__icon {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  width: 24px;
  height: 24px;
  font-size: 16px;
  color: #f6a21a;
  flex-shrink: 0;
}

.kb-upload-folder-option.is-root .kb-upload-folder-option__icon {
  color: #2563eb;
}

.kb-upload-folder-option__content {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.35;
}

.kb-upload-folder-option__name {
  overflow: hidden;
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #17233d;
}

.kb-upload-folder-option__path {
  overflow: hidden;
  margin-top: 2px;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #94a3b8;
}

.kb-upload-modal ::v-deep(.ant-upload.ant-upload-drag) {
  background: linear-gradient(180deg, #fcfdff 0%, #f8fbff 100%);
  border: 1px dashed #93c5fd;
  border-radius: 18px;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.kb-upload-modal ::v-deep(.ant-upload.ant-upload-drag:hover) {
  border-color: #60a5fa;
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.08);
}

.kb-upload-modal ::v-deep(.ant-upload.ant-upload-drag .ant-upload) {
  padding: 0;
}

.kb-upload-dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 30px 24px;
  text-align: center;
}

.kb-upload-dropzone-icon {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 64px;
  height: 64px;
  font-size: 28px;
  color: #3b82f6;
  background: linear-gradient(135deg, #dbeafe 0%, #eff6ff 100%);
  border-radius: 20px;
  box-shadow: 0 10px 24px rgba(59, 130, 246, 0.16);
}

.kb-upload-dropzone-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.45;
}

.kb-upload-dropzone-hint {
  margin: 0;
  max-width: 460px;
  font-size: 13px;
  color: #64748b;
  line-height: 1.7;
}

.kb-upload-selected {
  overflow: hidden;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
}

.kb-upload-selected-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  background: linear-gradient(180deg, #fcfdff 0%, #f8fafc 100%);
  border-bottom: 1px solid #eef2f6;
}

.kb-upload-selected-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.kb-upload-selected-head-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kb-upload-selected-head-main span {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.kb-upload-selected-head-main small {
  font-size: 12px;
  color: #64748b;
  line-height: 1.4;
}

.kb-upload-selected-count {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  padding: 0 10px;
  min-width: 48px;
  height: 28px;
  font-size: 12px;
  font-weight: 700;
  color: #1d4ed8;
  background: #eff6ff;
  border-radius: 999px;
}

.kb-upload-selected-list {
  display: flex;
  overflow: auto;
  max-height: 220px;
  flex-direction: column;
}

.kb-upload-selected-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  gap: 12px;
  border-bottom: 1px solid #f1f5f9;
}

.kb-upload-selected-item:last-child {
  border-bottom: none;
}

.kb-upload-selected-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.kb-upload-selected-file-icon {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 32px;
  height: 32px;
  color: #2563eb;
  background: #eff6ff;
  border-radius: 10px;
  flex-shrink: 0;
}

.kb-upload-selected-name {
  overflow: hidden;
  font-size: 13px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #0f172a;
}

.kb-upload-selected-size {
  font-size: 12px;
  color: #64748b;
  flex-shrink: 0;
}

.kb-upload-selected-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.kb-upload-file-progress {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 5px;
  min-width: 110px;

  ::v-deep(.ant-progress-line) {
    width: 100px;
    line-height: 1;
  }
}

.kb-upload-remove-btn {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  padding: 0;
  width: 30px;
  height: 30px;
  color: #94a3b8;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  transition: all 0.2s ease;
  cursor: pointer;
}

.kb-upload-remove-btn:disabled {
  color: #cbd5e1;
  background: #f8fafc;
  cursor: not-allowed;
}

.kb-upload-remove-btn:hover {
  color: #dc2626;
  background: #fef2f2;
  border-color: #fecaca;
}

@media (max-width: 900px) {
  .kd-v2 {
    grid-template-columns: 1fr;
  }

  .kd-v2-sidebar {
    border-right: none;
    border-bottom: 1px solid @border;
    max-height: 420px;
  }

  .kd-drawer-body {
    grid-template-columns: 1fr;
  }

  .kd-drawer-rail {
    flex-flow: row wrap;
    border-right: none;
    border-bottom: 1px solid @border;
  }
}
</style>
