package com.ludan.app.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.common.service.ISuperService;
import com.ludan.app.entity.KbQaPair;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;
import java.util.Map;

/**
 * 问答对 Service
 *
 * @author ludan
 */
public interface KbQaPairService extends ISuperService<KbQaPair> {

    Page<KbQaPair> findList(Map<String, Object> params);

    /**
     * 创建问答对
     */
    KbQaPair createQa(Long kbId, String question, String answer);

    /**
     * 更新问答对
     */
    void updateQa(Long qaId, String question, String answer);

    /**
     * CSV批量导入问答对
     */
    int importCsv(Long kbId, MultipartFile file);

    /**
     * 批量删除 QA 并触发一次 rebuildQaIndex 全量重建。
     */
    int deleteQas(Long kbId, List<Long> qaIds);
}
