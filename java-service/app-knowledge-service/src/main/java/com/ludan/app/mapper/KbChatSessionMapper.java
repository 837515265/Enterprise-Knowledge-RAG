package com.ludan.app.mapper;

import com.central.db.mapper.SuperMapper;
import com.ludan.app.entity.KbChatSession;
import org.apache.ibatis.annotations.Mapper;

/**
 * 问AI会话 Mapper
 *
 * @author ludan
 */
@Mapper
public interface KbChatSessionMapper extends SuperMapper<KbChatSession> {
}
