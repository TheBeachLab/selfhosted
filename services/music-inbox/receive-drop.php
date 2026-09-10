<?php
// Called over the existing authenticated SSH connection, as www-data.
define('OC_CONSOLE', true);
require '/var/www/nextcloud/lib/base.php';
set_exception_handler(function (Throwable $e) { fwrite(STDERR, $e->getMessage()."\n"); exit(1); });
$m=json_decode($argv[1],true,512,JSON_THROW_ON_ERROR);
if (!preg_match('/^[a-f0-9]{64}$/D',$m['sha256'] ?? '') || !is_int($m['size']) || $m['size']<=0) throw new Exception('Invalid content description');
$parts=explode('/',$m['relative']);
foreach($parts as $part) if ($part==='' || $part==='.' || $part==='..' || preg_match('/[\\\\\x00-\x1f]/',$part)) throw new Exception('Unsafe relative path');
$ext=strtolower(pathinfo(end($parts),PATHINFO_EXTENSION));
if (!in_array($ext,['mp3','m4a','flac','wav','aif','aiff','ogg','opus','aac','wma','ape'])) throw new Exception('Unsupported audio extension');
\OC::$server->getUserSession()->setUser(\OC::$server->getUserManager()->get('admin'));
\OC_Util::setupFS('admin');
$home=\OC::$server->get(\OCP\Files\IRootFolder::class)->getUserFolder('admin');
function digest($node) { $f=$node->fopen('r');$h=hash_init('sha256');hash_update_stream($h,$f);fclose($f);return hash_final($h); }
$state='/var/lib/music-inbox/drop-receipts';
if (!is_dir($state) && !mkdir($state,0700,true)) throw new Exception('Cannot create receipt directory');
$lock=fopen($state.'/'.$m['sha256'].'.lock','c');
if (!$lock || !flock($lock,LOCK_EX)) throw new Exception('Cannot lock upload');
$receipt=$state.'/'.$m['sha256'].'.json';
if (file_exists($receipt)) {
    $old=json_decode(file_get_contents($receipt),true,512,JSON_THROW_ON_ERROR);
    $nodes=$home->getById($old['file_id']);
    if (count($nodes)!==1) throw new Exception('Previously uploaded file no longer exists; keeping local source');
    $current=digest($nodes[0]);$valid=$current===$m['sha256'];
    $done='/var/lib/music-inbox/done/'.$old['file_id'].'.json';
    if (!$valid && file_exists($done)) {
        $d=json_decode(file_get_contents($done),true,512,JSON_THROW_ON_ERROR);
        $valid=($d['source']['sha256']??null)===$m['sha256'] && ($d['result']['sha256']??null)===$current;
    }
    if (!$valid) throw new Exception('Previously uploaded file changed unexpectedly; keeping local source');
    echo json_encode($old);exit;
}
$folder=$home->get('Music');
foreach(array_merge(['imported'],array_slice($parts,0,-1)) as $part) {
    $folder=$folder->nodeExists($part)?$folder->get($part):$folder->newFolder($part);
    if (!($folder instanceof \OCP\Files\Folder)) throw new Exception('Destination parent is not a folder');
}
$name=end($parts);$node=null;
if ($folder->nodeExists($name)) {
    $existing=$folder->get($name);
    if ($existing instanceof \OCP\Files\File && digest($existing)===$m['sha256']) $node=$existing;
    else $name=pathinfo($name,PATHINFO_FILENAME).' ['.substr($m['sha256'],0,12).'].'.$ext;
}
if ($node===null && $folder->nodeExists($name)) {
    $existing=$folder->get($name);
    if ($existing instanceof \OCP\Files\File && digest($existing)===$m['sha256']) $node=$existing;
    else throw new Exception('Destination collision; keeping local source');
}
if ($node===null) {
    $temp=$folder->newFile('.drop-'.bin2hex(random_bytes(12)).'.upload');
    try {
        $temp->putContent(STDIN);
        if ($temp->getSize()!=$m['size'] || digest($temp)!==$m['sha256']) throw new Exception('Upload verification failed');
        if ($folder->nodeExists($name)) throw new Exception('Destination created concurrently');
        $temp->move($folder->getPath().'/'.$name);$node=$temp;
    } catch (Throwable $e) { $temp->delete();throw $e; }
}
$result=['sha256'=>$m['sha256'],'size'=>$m['size'],'file_id'=>$node->getId(),'path'=>$home->getRelativePath($node->getPath()),'verified_at'=>date('c')];
$pending=$receipt.'.tmp';
if (file_put_contents($pending,json_encode($result,JSON_THROW_ON_ERROR))===false || !rename($pending,$receipt)) throw new Exception('Cannot persist upload receipt');
echo json_encode($result,JSON_THROW_ON_ERROR);
