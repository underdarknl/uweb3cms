SET FOREIGN_KEY_CHECKS=0;
DROP TABLE IF EXISTS `apiuser`;
CREATE TABLE `apiuser` (
  `ID` mediumint(8) unsigned NOT NULL AUTO_INCREMENT,
  `key` char(32) NOT NULL,
  `active` enum('true','false') NOT NULL DEFAULT 'true',
  `name` varchar(45) NOT NULL,
  `collectionfilter` varchar(255) DEFAULT NULL,
  `client` smallint(5) unsigned NOT NULL,
  PRIMARY KEY (`ID`),
  UNIQUE KEY `key_UNIQUE` (`key`),
  UNIQUE KEY `name` (`client`,`name`),
  KEY `client` (`client`,`active`),
  CONSTRAINT `apiuser_client` FOREIGN KEY (`client`) REFERENCES `client` (`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8;

DROP TABLE IF EXISTS `article`;
CREATE TABLE `article` (
  `ID` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(255) CHARACTER SET utf8 NOT NULL,
  `published` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `dateCreated` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `dateDeleted` datetime NOT NULL DEFAULT '1000-01-01 00:00:00',
  `client` smallint(5) unsigned NOT NULL,
  PRIMARY KEY (`ID`),
  UNIQUE KEY `title` (`name`,'dateDeleted',`client`),
  KEY `client` (`client`),
  CONSTRAINT `article_client` FOREIGN KEY (`client`) REFERENCES `client` (`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

DROP TABLE IF EXISTS `articleAtom`;
CREATE TABLE `articleAtom` (
  `article` int(11) unsigned NOT NULL,
  `atom` int(11) unsigned NOT NULL,
  `sortorder` smallint(5) unsigned NOT NULL,
  UNIQUE KEY `article_id` (`article`,`atom`),
  KEY `atom_id` (`atom`),
  CONSTRAINT `articleAtom_Article` FOREIGN KEY (`article`) REFERENCES `article` (`ID`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `articleAtom_Atom` FOREIGN KEY (`atom`) REFERENCES `atom` (`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

DROP TABLE IF EXISTS `atom`;
CREATE TABLE `atom` (
  `ID` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `key` varchar(255) CHARACTER SET utf8 DEFAULT NULL,
  `content` text COLLATE utf8_unicode_ci NOT NULL,
  `published` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `type` smallint(6) unsigned NOT NULL DEFAULT '1',
  PRIMARY KEY (`ID`),
  UNIQUE KEY `id` (`ID`),
  UNIQUE KEY `key` (`key`),
  KEY `atom_type_id` (`type`),
  CONSTRAINT `atom_type` FOREIGN KEY (`type`) REFERENCES `type` (`ID`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

DROP TABLE IF EXISTS `client`;
CREATE TABLE `client` (
  `ID` smallint(5) unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(45) NOT NULL,
  `active` enum('true','false') NOT NULL DEFAULT 'true',
  PRIMARY KEY (`ID`),
  KEY `active` (`active`)
) ENGINE=InnoDB AUTO_INCREMENT=0 DEFAULT CHARSET=utf8;

INSERT INTO `client`
(`ID`,
`name`,
`active`)
VALUES
(0,
'Base',
'true');
DROP TABLE IF EXISTS `collection`;
CREATE TABLE `collection` (
  `ID` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(80) COLLATE utf8_unicode_ci NOT NULL,
  `dateCreated` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `dateDeleted` datetime NOT NULL DEFAULT '1000-01-01 00:00:00',
  `client` smallint(5) unsigned NOT NULL,
  PRIMARY KEY (`ID`),
  UNIQUE KEY `name` (`name`,`dateDeleted`,`client`)
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

DROP TABLE IF EXISTS `collectionArticle`;
CREATE TABLE `collectionArticle` (
  `collection` int(11) unsigned NOT NULL,
  `article` int(11) unsigned NOT NULL,
  `sortorder` smallint(5) unsigned NOT NULL,
  `url` varchar(100) COLLATE utf8_unicode_ci DEFAULT NULL,
  `template` varchar(50) CHARACTER SET utf8 DEFAULT 'default',
  `meta` varchar(255) COLLATE utf8_unicode_ci DEFAULT '',
  UNIQUE KEY `collection` (`collection`,`article`),
  UNIQUE KEY `url` (`collection`,`url`),
  KEY `article` (`article`),
  CONSTRAINT `collectionArticle_article` FOREIGN KEY (`article`) REFERENCES `article` (`ID`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `collectionArticle_collection` FOREIGN KEY (`collection`) REFERENCES `collection` (`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

DROP TABLE IF EXISTS `menu`;
CREATE TABLE `menu` (
  `ID` smallint(5) unsigned NOT NULL AUTO_INCREMENT,
  `client` smallint(5) unsigned NOT NULL,
  `collection` int(11) unsigned NOT NULL,
  `name` varchar(50) NOT NULL,
  `dateCreated` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `dateDeleted` datetime NOT NULL DEFAULT '1000-01-01 00:00:00',
  PRIMARY KEY (`ID`),
  UNIQUE KEY `name` (`client`,`collection`,`name`,`dateDeleted`),
  CONSTRAINT `menu_client` FOREIGN KEY (`client`) REFERENCES `client` (`ID`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `menu_collection` FOREIGN KEY (`collection`) REFERENCES `collection` (`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

DROP TABLE IF EXISTS `menuArticle`;
CREATE TABLE `menuArticle` (
  `ID` smallint(5) unsigned NOT NULL AUTO_INCREMENT,
  `menu` smallint(5) unsigned NOT NULL,
  `article` int(11) unsigned NOT NULL,
  `sortorder` smallint(5) unsigned NOT NULL,
  `name` varchar(50) CHARACTER SET utf8 DEFAULT NULL,
  PRIMARY KEY (`ID`),
  KEY `article` (`article`),
  CONSTRAINT `menuArticle_article` FOREIGN KEY (`article`) REFERENCES `article` (`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

DROP TABLE IF EXISTS `type`;
CREATE TABLE `type` (
  `ID` smallint(5) unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(45) DEFAULT NULL,
  `schema` text,
  `template` text,
  `dateCreated` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `dateDeleted` datetime NOT NULL DEFAULT '1000-01-01 00:00:00',
  `client` smallint(5) unsigned DEFAULT NULL,
  PRIMARY KEY (`ID`),
  UNIQUE KEY `name` (`name`,`dateDeleted`,`client`),
  KEY `type_client` (`client`),
  CONSTRAINT `type_client` FOREIGN KEY (`client`) REFERENCES `client` (`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8;

DROP TABLE IF EXISTS `user`;
CREATE TABLE `user` (
  `ID` mediumint(8) unsigned NOT NULL AUTO_INCREMENT,
  `email` varchar(255) NOT NULL,
  `password` char(100) NOT NULL,
  `client` smallint(5) unsigned NOT NULL,
  `active` enum('true','false') NOT NULL DEFAULT 'true',
  PRIMARY KEY (`ID`),
  UNIQUE KEY `email` (`email`),
  KEY `login` (`email`,`password`,`active`),
  KEY `client` (`client`),
  KEY `active` (`active`),
  CONSTRAINT `user_client` FOREIGN KEY (`client`) REFERENCES `client` (`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8;

DROP TABLE IF EXISTS `variable`;
CREATE TABLE `variable` (
  `ID` smallint(5) unsigned NOT NULL AUTO_INCREMENT,
  `tag` varchar(100) COLLATE utf8_unicode_ci NOT NULL,
  `value` varchar(255) COLLATE utf8_unicode_ci NOT NULL,
  `client` smallint(5) unsigned NOT NULL,
  PRIMARY KEY (`ID`),
  KEY `tag` (`tag`),
  KEY `client` (`client`),
  CONSTRAINT `variable_client` FOREIGN KEY (`client`) REFERENCES `client` (`ID`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;
SET FOREIGN_KEY_CHECKS=1;
