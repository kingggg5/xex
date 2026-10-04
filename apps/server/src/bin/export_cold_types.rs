fn main() {
    let output=std::env::args().nth(1).expect("explicit external output file");
    std::fs::write(output,aetherfield_server::cold::typescript_bindings()).expect("write generated DTO");
}
