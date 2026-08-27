package com.ludan.app.mapper;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.central.db.mapper.SuperMapper;
import com.ludan.app.entity.KbChunk;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

/**
 * Chunk 主数据 Mapper
 *
 * @author ludan
 */
@Mapper
public interface KbChunkMapper extends SuperMapper<KbChunk> {

    Page<KbChunk> findByFileNode(Page<KbChunk> page, @Param("p") Map<String, Object> params);

    /**
     * 按主键物理删除 Chunk（绕过逻辑删除）。
     */
    @Delete("DELETE FROM kb_chunk WHERE id = #{id}")
    int physicalDeleteById(@Param("id") Long id);

    /**
     * 按文件节点批量物理删除 Chunk（绕过逻辑删除）。
     */
    @Delete("<script>"
            + "DELETE FROM kb_chunk WHERE file_node_id IN "
            + "<foreach collection='fileNodeIds' item='id' open='(' separator=',' close=')'>#{id}</foreach>"
            + "</script>")
    int physicalDeleteByFileNodeIds(@Param("fileNodeIds") List<Long> fileNodeIds);
}
