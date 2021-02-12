<?php
include('cms.php');

// variables that can be cached between users for this site
$cachable = array('name'=>'examplesite',
                  'url'=>'http://www.examplesite.nl',
                  'shorturl'=>'examplesite.nl');

// variables that should not be cached, but instead should be replaces for every new request
$uncachable = array('urlvar'=>'1',
                    'anothervar'=>'test');

// get the cms instance
$cms = new CMS('somecollection.com',
               array('http://127.0.0.1:8000'),
               $cachable,
               $uncachable,
               '/tmp/phpcms/'.$cachable['name']);


//  header stuff
$menuitems = $cms->GetMenu();
echo '<ul>';
foreach($menuitems as $menuitem){
  echo '<li><a href="'.$menuitem->menuname.'">'.$menuitem->menuname.'</a></li>';
}
echo '</ul>';
