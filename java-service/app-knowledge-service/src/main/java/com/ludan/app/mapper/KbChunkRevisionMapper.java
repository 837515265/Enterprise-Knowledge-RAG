package com.ludan.app.mapper;

import com.central.db.mapper.SuperMapper;
import com.ludan.app.entity.KbChunkRevision;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

/**
 * Chunk 版本 Mapper
 *
 * @author ludan
 */
@Mapper
public interface KbChunkRevisionMapper extends SuperMapper<KbChunkRevision> {

    /**
     * 获取指定 chunk 的最大版本号
     */
    Integer getMaxRevisionNo(@Param("chunkId") Long chunkId);

    /**
     * 按 Chunk 物理删除全部版本。
     */
    @Delete("DELETE FROM kb_chunk_revision WHERE chunk_id = #{chunkId}")
    int physicalDeleteByChunkId(@Param("chunkId") Long chunkId);

    /**
     * 按文件节点批量物理删除版本。
     */
    @Delete("<script>"
            + "DELETE FROM kb_chunk_revision WHERE file_node_id IN "
            + "<foreach collection='fileNodeIds' item='id' open='(' separator=',' close=')'>#{id}</foreach>"
            + "</script>")
    int physicalDeleteByFileNodeIds(@Param("fileNodeIds") List<Long> fileNodeIds);
}
