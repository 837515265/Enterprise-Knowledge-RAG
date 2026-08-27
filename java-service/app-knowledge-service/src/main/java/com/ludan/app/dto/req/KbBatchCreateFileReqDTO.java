package com.ludan.app.dto.req;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

import java.util.List;

/**
 * 批量新增知识库文件请求体。
 *
 * @author GPT-5.4
 */
@Data
public class KbBatchCreateFileReqDTO {

    @ApiModelProperty("父节点ID，根目录可为空")
    private Long parentId;

    @ApiModelProperty("解析策略配置ID，为空时使用知识库默认策略")
    private String parseStrategyConfigId;

    @ApiModelProperty("待入库文件列表")
    private List<UploadedFileItem> files;

    /**
     * 已上传文件项。
     */
    @Data
    public static class UploadedFileItem {

        @ApiModelProperty("通用文件上传返回的 fileId")
        private String fileId;

        @ApiModelProperty("展示名称")
        private String fileName;

        @ApiModelProperty("原始文件名")
        private String originalName;

        @ApiModelProperty("文件字节数")
        private Long fileSize;

        @ApiModelProperty("MIME 类型")
        private String mimeType;

        @ApiModelProperty("文件扩展名")
        private String fileExt;

        @ApiModelProperty("文件哈希")
        private String fileHash;

        @ApiModelProperty("是否开启多模态解析（图文文档提图 + VLM 描述），true 时解析时带 parse_options.multimodal.enabled")
        private Boolean multimodalEnabled;
    }
}
