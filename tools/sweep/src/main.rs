use xexoria_sweep::{
    config::{Config, HELP},
    runner,
};
#[tokio::main]
async fn main() {
    let code = match Config::parse(std::env::args().skip(1)) {
        Ok(None) => {
            println!("{HELP}");
            0
        }
        Ok(Some(c)) => match runner::run(c).await {
            Ok(true) => 0,
            Ok(false) => 2,
            Err(e) => {
                eprintln!("Sweep stopped: {e}");
                1
            }
        },
        Err(e) => {
            eprintln!("{e}\n{HELP}");
            1
        }
    };
    std::process::exit(code);
}
