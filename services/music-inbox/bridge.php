<?php
// Nextcloud 32 file API preserves IDs, hooks and cache entries during moves.
define('OC_CONSOLE', true);
require '/var/www/nextcloud/lib/base.php';
set_exception_handler(function(\Throwable $error) { fwrite(STDERR,$error->getMessage()."\n"); exit(1); });
\OC::$server->getUserSession()->setUser(\OC::$server->getUserManager()->get('admin'));
\OC_Util::setupFS('admin');
$home = \OC::$server->get(\OCP\Files\IRootFolder::class)->getUserFolder('admin');
$music = $home->get('Music');
$input = json_decode(stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);
function digest($node) { $f=$node->fopen('r'); $h=hash_init('sha256'); hash_update_stream($h,$f); fclose($f); return hash_final($h); }
function folder($parent, $relative) {
    foreach (explode('/', $relative) as $part) {
        if ($part === '' || $part === '.' || $part === '..') throw new Exception('Invalid path');
        $parent = $parent->nodeExists($part) ? $parent->get($part) : $parent->newFolder($part);
        if (!($parent instanceof \OCP\Files\Folder)) throw new Exception('Not a folder');
    }
    return $parent;
}
switch ($input['op']) {
case 'initialize':
    $inbox = $music->nodeExists('imported') ? $music->get('imported') : $music->newFolder('imported');
    $nodes = array_filter($music->getDirectoryListing(), fn($n)=>$n->getName() !== 'imported' && $n->getName() !== 'import-status.md');
    foreach ($nodes as $n) if ($inbox->nodeExists($n->getName())) throw new Exception('Inbox collision');
    foreach ($nodes as $n) $n->move($inbox->getPath().'/'.$n->getName());
    echo json_encode(['moved_folders'=>count($nodes)]); break;
case 'list':
    $rows=[];
    $walk=function($node) use (&$walk,&$rows,$home) {
        if ($node instanceof \OCP\Files\Folder) {foreach ($node->getDirectoryListing() as $child) $walk($child);}
        else $rows[]=['id'=>$node->getId(),'path'=>$home->getRelativePath($node->getPath()),'size'=>$node->getSize(),'mtime'=>$node->getMTime()];
    };
    if ($music->nodeExists('imported')) $walk($music->get('imported'));
    echo json_encode($rows,JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR); break;
case 'apply':
    $nodes=$home->getById((int)$input['id']);
    if (count($nodes)!==1) throw new Exception('Source ID not unique');
    $node=$nodes[0];
    if (!str_starts_with($node->getPath(),$music->getPath().'/imported/')) throw new Exception('Source outside inbox');
    if (digest($node)!==$input['sha256']) throw new Exception('Source changed');
    $dest=$input['destination'];
    if (str_starts_with($dest,'/') || str_contains($dest,'..') || str_starts_with($dest,'imported/')) throw new Exception('Unsafe destination');
    $parent=folder($music,dirname($dest));
    if ($parent->nodeExists(basename($dest))) throw new Exception('Destination exists; retained for review');
    $stage=realpath($input['stage']);
    if (!$stage || !str_starts_with($stage,'/var/lib/music-inbox/stage/')) throw new Exception('Stage outside allowed path');
    if (hash_file('sha256',$stage)!==$input['staged_sha256']) throw new Exception('Stage changed');
    $f=fopen($stage,'rb'); $node->putContent($f); if (is_resource($f)) fclose($f);
    if (digest($node)!==$input['staged_sha256']) throw new Exception('Written content mismatch');
    $node->move($parent->getPath().'/'.basename($dest));
    echo json_encode(['id'=>$node->getId(),'path'=>$home->getRelativePath($node->getPath()),'sha256'=>digest($node)]); break;
case 'report':
    $node=$music->nodeExists('import-status.md') ? $music->get('import-status.md') : $music->newFile('import-status.md');
    $node->putContent($input['text']); echo '{}'; break;
default: throw new Exception('Unknown operation');
}
