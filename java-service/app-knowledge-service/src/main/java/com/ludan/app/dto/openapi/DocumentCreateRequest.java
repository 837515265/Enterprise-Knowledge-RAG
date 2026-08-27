package com.ludan.app.dto.openapi;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

import java.util.List;

@Data
public class DocumentCreateRequest {

    @ApiModelProperty("父目录ID，为空则存于根目录")
    private Long parentId;

    @ApiModelProperty(value = "待入库文件列表", required = true)
    private List<FileItem> files;

    @Data
    public static class FileItem {

        @ApiModelProperty(value = "文件中心 fileId", required = true)
        private String fileId;

        @ApiModelProperty(value = "展示名称", required = true)
        private String fileName;

        @ApiModelProperty("原始文件名")
        private String originalName;

        @ApiModelProperty("文件字节数")
        private Long fileSize;

        @ApiModelProperty("MIME 类型")
        private String mimeType;

        @ApiModelProperty("扩展名")
        private String fileExt;
    }
}
