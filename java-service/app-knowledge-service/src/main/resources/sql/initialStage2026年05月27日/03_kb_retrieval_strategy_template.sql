-- MySQL dump 10.13  Distrib 5.7.18, for macos10.12 (x86_64)
--
-- Host: 10.10.20.92    Database: ai_contract
-- ------------------------------------------------------
-- Server version	8.0.22

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Dumping data for table `kb_retrieval_strategy_config`
--
-- WHERE:  scope_type='template' AND del_flag=0

LOCK TABLES `kb_retrieval_strategy_config` WRITE;
/*!40000 ALTER TABLE `kb_retrieval_strategy_config` DISABLE KEYS */;
INSERT INTO `kb_retrieval_strategy_config` VALUES ('retrieval_balanced','均衡检索策略','balanced','template',NULL,'{\"topK\": 8, \"hybrid\": true, \"qaWeight\": 0.5, \"chunkWeight\": 0.5, \"rerankEnabled\": true, \"scoreThreshold\": 0.45}','active','默认推荐，兼顾召回与精准度',NULL,'2026-04-26 14:58:46',NULL,'6bdd1110-15de-40ef-b03d-d88fd8245da6',NULL,'管理员',0),('retrieval_precision','精准优先策略','precision','template',NULL,'{\"topK\": 5, \"hybrid\": true, \"qaWeight\": 0.6, \"chunkWeight\": 0.4, \"rerankEnabled\": true, \"scoreThreshold\": 0.65}','active','适合要求答案严格命中文档依据的场景',NULL,'2026-04-28 09:18:35',NULL,'6bdd1110-15de-40ef-b03d-d88fd8245da6',NULL,'管理员',0),('retrieval_recall','召回优先策略','recall','template',NULL,'{\"topK\": 12, \"hybrid\": true, \"qaWeight\": 0.4, \"chunkWeight\": 0.6, \"rerankEnabled\": true, \"scoreThreshold\": 0.35}','disabled','适合需要覆盖更多候选材料的场景',NULL,'2026-04-28 09:18:37',NULL,'6bdd1110-15de-40ef-b03d-d88fd8245da6',NULL,'管理员',0);
/*!40000 ALTER TABLE `kb_retrieval_strategy_config` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-05-13 14:48:37
