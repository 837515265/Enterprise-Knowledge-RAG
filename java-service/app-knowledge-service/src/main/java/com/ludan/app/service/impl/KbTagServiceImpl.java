package com.ludan.app.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.central.common.service.impl.SuperServiceImpl;
import com.ludan.app.entity.KbTag;
import com.ludan.app.mapper.KbTagMapper;
import com.ludan.app.service.KbTagService;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 知识库标签 Service 实现
 *
 * @author ludan
 */
@Service
public class KbTagServiceImpl
        extends SuperServiceImpl<KbTagMapper, KbTag>
        implements KbTagService {

    @Override
    public List<KbTag> findAll() {
        return this.list(new LambdaQueryWrapper<KbTag>().orderByDesc(KbTag::getCreateTime));
    }

    @Override
    public KbTag createTag(String name) {
        long count = this.count(new LambdaQueryWrapper<KbTag>().eq(KbTag::getName, name));
        if (count > 0) {
            throw new RuntimeException("标签名称已存在: " + name);
        }
        KbTag tag = new KbTag();
        tag.setName(name);
        this.save(tag);
        return tag;
    }
}
