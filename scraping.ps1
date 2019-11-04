$arr_kyoku = @("tbs", "nhk")
$hash_kyoku_method = @{tbs = "scrape"; nhk = "api"}
$today = Get-Date -UFormat "%Y%m%d"

function get_program_guide_by_scraping($kyoku, $filepath)
{
    #Write-Host $filepath
    cd C:\Users\eriko\Documents\workspace\ws_news_bot\news
    scrapy crawl tbs -o $filepath --nolog
    cd C:\Users\eriko\Documents\workspace\ws_news_bot
}

function get_program_guide_by_api($kyoku, $filepath)
{
    # TODO: 実装
    #Write-Host $filepath
}

activate newsbot
# TODO: 並列処理にする
foreach  ($kyoku in $arr_kyoku) {
    $filepath = $kyoku + "_news_" + $today + ".csv"
    if ($hash_kyoku_method[$kyoku] -eq "scrape") {
        get_program_guide_by_scraping $kyoku $filepath
    } else {
        get_program_guide_by_api $kyoku $filepath
    }
    $status = $?
    #TODO: 失敗したら通知する
}
deactivate
