-- 将问AI会话用户ID改为字符串，匹配用户中心的真实 userId。
ALTER TABLE `kb_chat_session`
  MODIFY COLUMN `user_id` VARCHAR(64) NOT NULL COMMENT '用户ID';
