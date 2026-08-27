package com.ludan.app.mapper;

import com.central.db.mapper.SuperMapper;
import com.ludan.app.entity.KbChatMessage;
import org.apache.ibatis.annotations.Mapper;

/**
 * 问AI消息 Mapper
 *
 * @author ludan
 */
@Mapper
public interface KbChatMessageMapper extends SuperMapper<KbChatMessage> {
}
