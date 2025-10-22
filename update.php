<?php
header('Content-Type: application/json; charset=utf-8');

// (optioneel) secret check — stel in via PHP-instellingen → extra env var: TRACKER_SECRET
$expected = getenv('TRACKER_SECRET');
if ($expected && ($_SERVER['HTTP_X_TRACKER_SECRET'] ?? '') !== $expected) {
    http_response_code(401);
    echo json_encode(['error' => 'unauthorized']);
    exit;
}

// Input lezen
$raw = file_get_contents('php://input');
$in = json_decode($raw, true);
if (!is_array($in))
    $in = [];
$in = array_merge($_GET, $_POST, $in);

$lat = $in['lat'] ?? $in['latitude'] ?? null;
$lon = $in['lon'] ?? $in['lng'] ?? $in['longitude'] ?? null;
$spdK = $in['speed_kmh'] ?? null;
$spdM = $in['speed'] ?? $in['spd'] ?? null;

if ($lat === null || $lon === null) {
    http_response_code(400);
    echo json_encode(['error' => 'lat/lon required']);
    exit;
}
$lat = (float) $lat;
$lon = (float) $lon;

$speed_kmh = null;
if ($spdK !== null && $spdK !== '')
    $speed_kmh = (float) $spdK;
elseif ($spdM !== null && $spdM !== '')
    $speed_kmh = (float) $spdM * 3.6;

$out = [
    'lat' => $lat,
    'lon' => $lon,
    'speed_kmh' => is_null($speed_kmh) ? null : round($speed_kmh, 1),
    'ts_client' => $in['timestamp'] ?? $in['time'] ?? null,
    'server_ts' => date('Y-m-d H:i:s'),
    'server_ts_iso' => gmdate('c'),
    'source' => $_SERVER['REMOTE_ADDR'] ?? null,
];

$file = __DIR__ . '/data.json';
$tmp = $file . '.tmp';
file_put_contents($tmp, json_encode($out, JSON_UNESCAPED_UNICODE));
rename($tmp, $file);

echo json_encode(['status' => 'ok', 'saved' => $out], JSON_UNESCAPED_UNICODE);