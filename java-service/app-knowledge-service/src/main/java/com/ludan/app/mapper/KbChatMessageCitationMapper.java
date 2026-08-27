package com.ludan.app.mapper;

import com.central.db.mapper.SuperMapper;
import com.ludan.app.entity.KbChatMessageCitation;
import org.apache.ibatis.annotations.Mapper;

/**
 * 消息引用 Mapper
 *
 * @author ludan
 */
@Mapper
public interface KbChatMessageCitationMapper extends SuperMapper<KbChatMessageCitation> {
}
