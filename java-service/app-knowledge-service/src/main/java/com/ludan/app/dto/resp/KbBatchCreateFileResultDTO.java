package com.ludan.app.dto.resp;

import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

/**
 * 批量新增知识库文件的单文件处理结果。
 *
 * @author GPT-5
 */
@Data
public class KbBatchCreateFileResultDTO {

    public static final String STATUS_SUCCESS = "SUCCESS";
    public static final String STATUS_DUPLICATE = "DUPLICATE";
    public static final String STATUS_FAILED = "FAILED";

    @ApiModelProperty("通用文件上传返回的 fileId")
    private String fileId;

    @ApiModelProperty("文件展示名称")
    private String fileName;

    @ApiModelProperty("文件 SHA-256")
    private String fileHash;

    @ApiModelProperty("处理状态：SUCCESS/DUPLICATE/FAILED")
    private String status;

    @ApiModelProperty("处理结果说明")
    private String message;

    public static KbBatchCreateFileResultDTO success(String fileId, String fileName, String fileHash) {
        return of(fileId, fileName, fileHash, STATUS_SUCCESS, "上传成功");
    }

    public static KbBatchCreateFileResultDTO duplicate(String fileId, String fileName, String fileHash) {
        return of(fileId, fileName, fileHash, STATUS_DUPLICATE, "文件已存在，已跳过");
    }

    public static KbBatchCreateFileResultDTO failed(String fileId, String fileName, String fileHash, String message) {
        return of(fileId, fileName, fileHash, STATUS_FAILED, message);
    }

    private static KbBatchCreateFileResultDTO of(String fileId, String fileName, String fileHash,
                                                String status, String message) {
        KbBatchCreateFileResultDTO result = new KbBatchCreateFileResultDTO();
        result.setFileId(fileId);
        result.setFileName(fileName);
        result.setFileHash(fileHash);
        result.setStatus(status);
        result.setMessage(message);
        return result;
    }
}
