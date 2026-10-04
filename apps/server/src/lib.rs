//! Aetherfield local room library (V5-02).
//!
//! The binary (`main.rs`) is a thin shell over this library so fuzz targets,
//! integration tests and future tools can link the simulation, codecs and
//! room without booting the server.

pub mod auth;
pub mod character;
pub mod chat_moderation;
pub mod combat_rules;
pub mod hero_skill_catalog;
pub mod inventory_instances;
pub mod mage_trial;
#[cfg(test)]
mod chat_moderation_routes_tests;
pub mod community;
pub mod cold;
pub mod content;
pub mod coordinate_fixture;
pub mod dungeon;
pub mod grounded_city;
#[cfg(test)]
mod blueprint_candidate_tests;
pub mod oauth;
pub mod room;
pub mod social;
pub mod storage;
pub mod interest;
pub mod wire;
pub mod world;
pub mod tick_profile;
pub mod sweep_fixture;
