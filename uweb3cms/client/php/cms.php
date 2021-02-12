<?php

class CMS{
  public $collection;
  public $servers;
  public $cachable;
  public $uncachable;
  private $server;

  public function __construct($collection, $servers, $cachable, $uncachable) {
    if(!is_array($servers)){
      throw new Exception('No CMS servers listed, array expected');
    }
    shuffle($servers);
    $this->servers = $servers;
    $this->collection = $collection;
    $this->cachable = $cachable;
    $this->uncachable = $uncachable;
  }

  private function _Connect($url){
    if(!$this->server){
      while(count($this->servers) > 0){
        $server = array_pop($this->servers);
        $fp = fopen($server.$url,'r');
        if($fp){
          $this->server = $server;
          break;
        }
      }
    }
    if(!$this->server){
      throw new Exception('No CMS servers reachable');
    }
    $contents = stream_get_contents($fp);
    fclose($fp);
    return $content;
  }

  public function GetMenu(){
    $json = json_decode($this->_Connect('/json/collection/'.$this->collection));
    $articles = array();
    foreach($json->articles as $article){
      if($article->menuname != null &&
         $article->visible){
        $articles[$article->sortorder] = $article;
      }
    }
    return $articles;
  }

  public function GetArticle($article, $raw=false){
    $json = json_decode($this->_Connect('/json/article/'.$article.($raw?'?raw=true':''));
    $atoms = array();
    foreach($json->atoms->key as $key){
      $json->atoms->key[$key] = &$json->atoms->sort[$key];
    }
    foreach($json->atoms->id as $id){
      $json->atoms->key[$id] = &$json->atoms->sort[$id];
    }
    return $atoms;
  }
}

class CachingCMS extends CMS{
  public $cachedir;
  private $_cachedir;

  public function __construct($collection, $servers, $cachable, $uncachable) {
    parent::__construct($collection, $servers, $cachable, $uncachable);

    if (is_dir($dir) && is_writable($dir)) {
      $this->cachedir = $cachedir;
      $this->_cachedir = opendir($cachedir);
    } else {
      throw new Exception($cachedir . ' is not a dir or not writable');
    }
  }
}
