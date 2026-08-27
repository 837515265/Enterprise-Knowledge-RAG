package com.ludan.app.service;

import com.central.common.service.ISuperService;
import com.ludan.app.dto.req.KbBatchCreateFileReqDTO;
import com.ludan.app.dto.resp.KbBatchCreateFileResultDTO;
import com.ludan.app.entity.KbFileNode;

import java.util.List;

/**
 * 文件节点 Service
 *
 * @author ludan
 */
public interface KbFileNodeService extends ISuperService<KbFileNode> {

    /**
     * 获取文件树（递归构建）
     */
    List<KbFileNode> getFileTree(Long kbId);

    /**
     * 创建文件节点（上传文件后记录元数据）
     */
    KbFileNode createFileNode(Long kbId, Long parentId, String fileId, String fileName, String originalName,
                              Long fileSize, String mimeType, String fileExt, String fileHash,
                              String parseStrategyConfigId, Integer multimodalEnabled);

    /**
     * 批量创建文件节点。
     */
    List<KbBatchCreateFileResultDTO> batchCreateFileNodes(Long kbId, Long parentId, String parseStrategyConfigId,
                                                          List<KbBatchCreateFileReqDTO.UploadedFileItem> files);

    /**
     * 创建文件夹节点
     */
    KbFileNode createFolderNode(Long kbId, Long parentId, String folderName);

    /**
     * 重命名文件/文件夹节点。
     */
    void renameNode(Long kbId, Long fileNodeId, String nodeName);

    /**
     * 移动文件或文件夹到指定父目录。
     */
    void moveNode(Long kbId, Long fileNodeId, Long targetParentId);

    /**
     * 删除文件或文件夹：递归硬删节点，并级联硬删下属 Chunk/Revision，尽力清理文件向量索引。
     */
    void deleteNode(Long kbId, Long fileNodeId);

    /**
     * 触发重新解析
     */
    void triggerReparse(Long kbId, Long fileNodeId);

    /**
     * 触发知识库下所有文件节点的重新解析。
     *
     * @return 触发重解析的文件数量
     */
    int triggerReparseAll(Long kbId);

    /**
     * 触发指定目录（含子目录）下所有文件节点的重新解析。
     *
     * @param kbId     知识库 ID
     * @param folderId 文件夹 ID
     * @return 触发重解析的文件数量
     */
    int triggerReparseAll(Long kbId, Long folderId);
}
