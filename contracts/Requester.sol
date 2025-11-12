// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/Counters.sol";

import "./DataTypes.sol";
import "./JobContract.sol";

contract Requester {
    address public owner;
    address public DAOManager;
    DataTypes.Evaluation[]  public  evaluations;

    uint256[] internal pendingOffersIDs;
    mapping(uint256 => DataTypes.Offer) private pendingOffers;

    address[] internal jobsAddress;
    mapping(address => JobContract) private jobContracts;

    modifier onlyOwner {
      require(msg.sender == owner,  "Only owner");
      _;
    }

    modifier onlyDAO {
      require(msg.sender == DAOManager, "Only DAO");
      _;
    }

    constructor(address payable ownerAddress) {
        DAOManager    = msg.sender;
        owner         = ownerAddress;
    }

    function newContract(JobContract newJobContract) external onlyDAO {
        insertContract(newJobContract);
    }

    function insertContract(JobContract newJobContract) internal {
        jobContracts[address(newJobContract)] = newJobContract;
        jobsAddress.push(address(newJobContract));
    }
}