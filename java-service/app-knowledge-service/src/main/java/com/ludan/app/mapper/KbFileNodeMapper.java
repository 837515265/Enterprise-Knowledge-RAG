package com.ludan.app.mapper;

import com.central.db.mapper.SuperMapper;
import com.ludan.app.entity.KbFileNode;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

/**
 * 文件节点 Mapper
 *
 * @author ludan
 */
@Mapper
public interface KbFileNodeMapper extends SuperMapper<KbFileNode> {

    /**
     * 查询指定知识库下的文件树节点
     */
    List<KbFileNode> selectByKbId(@Param("kbId") Long kbId, @Param("parentId") Long parentId);

    /**
     * 按文件节点聚合待审核 Chunk 数量
     */
    List<Map<String, Object>> selectPendingChunkCounts(@Param("kbId") Long kbId);

    /**
     * 按主键批量物理删除文件节点（绕过逻辑删除）。
     */
    @Delete("<script>"
            + "DELETE FROM kb_file_node WHERE id IN "
            + "<foreach collection='ids' item='id' open='(' separator=',' close=')'>#{id}</foreach>"
            + "</script>")
    int physicalDeleteByIds(@Param("ids") List<Long> ids);
}
