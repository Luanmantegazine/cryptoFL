// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import "./DataTypes.sol";
import "./JobContract.sol";

contract Requester {
    address public owner;                           // Endereço da carteira do Trainer
    address public DAOManager;                      // Manager é o endereço do contrato que faz o gerenciamento da DAO
    DataTypes.Evaluation[]  public  evaluations;    // List of received evaluation
    uint256 public rating;
    uint256 private evaluationCount;
    uint256 private cumulativeScore;

    uint256[] internal pendingOffersIDs;
    mapping(uint256 => DataTypes.Offer) private pendingOffers; //<offerID, Offer> Ofertas de trabalho que estão aguardando resposta.

    address[] internal jobsAddress;
    mapping(address => JobContract) private jobContracts;   // Contratos de trabalho

    modifier onlyOwner {
      require(msg.sender == owner,  "Only owner");
      _;
    }

    modifier onlyDAO {
      require(msg.sender == DAOManager, "Only DAO");
      _;
    }

    constructor(address ownerAddress) {
        DAOManager    = msg.sender;
        owner         = ownerAddress;
        rating        = 10;
    }

    function newContract(JobContract newJobContract) external onlyDAO {
        insertContract(newJobContract);
    }

    function insertContract(JobContract newJobContract) internal {
        jobContracts[address(newJobContract)] = newJobContract;
        jobsAddress.push(address(newJobContract));
    }

    function recordEvaluation(int256 score, string calldata comment) external onlyDAO {
        require(score >= 0 && score <= 10, "Score out of bounds");

        evaluations.push(DataTypes.Evaluation({comment: comment, rating: score}));
        cumulativeScore += uint256(int256(score));
        evaluationCount += 1;

        rating = cumulativeScore / evaluationCount;
    }
}
